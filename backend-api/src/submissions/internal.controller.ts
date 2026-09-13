import { Body, Controller, Get, Headers, Param, Patch, UnauthorizedException, Inject, NotFoundException } from '@nestjs/common';
import { Pool } from 'pg';
import { PG_POOL } from '../db/db.module';

interface TestCaseResultInput {
  testCaseId: string;
  passed: boolean;
  actualOutput?: string;
  runtimeMs?: number;
}

@Controller('internal/submissions')
export class InternalSubmissionsController {
  constructor(@Inject(PG_POOL) private db: Pool) {}

  private checkToken(token?: string) {
    if (!token || token !== process.env.JUDGE_INTERNAL_TOKEN) {
      throw new UnauthorizedException('Invalid internal token');
    }
  }

  @Get(':id')
  async getSubmission(@Param('id') id: string, @Headers('x-internal-token') token: string) {
    this.checkToken(token);
    const res = await this.db.query('SELECT * FROM submissions WHERE id = $1', [id]);
    if (!res.rows[0]) throw new NotFoundException('Submission not found');
    return res.rows[0];
  }

  @Patch(':id/verdict')
  async setVerdict(
    @Param('id') id: string,
    @Headers('x-internal-token') token: string,
    @Body()
    body: {
      status: 'completed' | 'infra_error';
      verdict: string;
      score: number;
      runtimeMs?: number;
      memoryKb?: number;
      judgeImageVersion: string;
      errorDetail?: string;
      testCaseResults: TestCaseResultInput[];
    },
  ) {
    this.checkToken(token);

    const client = await this.db.connect();
    try {
      await client.query('BEGIN');

      // Idempotency guard: if this submission was already judged, don't
      // re-apply a second (possibly retried) verdict on top of it.
      const current = await client.query('SELECT status FROM submissions WHERE id = $1 FOR UPDATE', [id]);
      if (!current.rows[0]) throw new Error('Submission not found');
      if (current.rows[0].status === 'completed' || current.rows[0].status === 'infra_error') {
        await client.query('ROLLBACK');
        return { alreadyJudged: true };
      }

      await client.query(
        `UPDATE submissions SET status=$1, verdict=$2, score=$3, runtime_ms=$4, memory_kb=$5,
         judge_image_version=$6, error_detail=$7, judged_at=now() WHERE id=$8`,
        [
          body.status,
          body.verdict,
          body.score,
          body.runtimeMs ?? null,
          body.memoryKb ?? null,
          body.judgeImageVersion,
          body.errorDetail ?? null,
          id,
        ],
      );

      for (const tcr of body.testCaseResults ?? []) {
        await client.query(
          `INSERT INTO test_case_results (submission_id, test_case_id, passed, actual_output, runtime_ms)
           VALUES ($1,$2,$3,$4,$5)`,
          [id, tcr.testCaseId, tcr.passed, tcr.actualOutput ?? null, tcr.runtimeMs ?? null],
        );
      }

      await client.query('COMMIT');
      return { ok: true };
    } catch (e) {
      await client.query('ROLLBACK');
      throw e;
    } finally {
      client.release();
    }
  }
}
