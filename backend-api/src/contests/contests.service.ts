import { ForbiddenException, Inject, Injectable, NotFoundException } from '@nestjs/common';
import { Pool } from 'pg';
import { PG_POOL } from '../db/db.module';

@Injectable()
export class ContestsService {
  constructor(@Inject(PG_POOL) private db: Pool) {}

  async createContest(orgId: string, title: string, startsAt: string, endsAt: string) {
    const res = await this.db.query(
      `INSERT INTO contests (org_id, title, starts_at, ends_at) VALUES ($1,$2,$3,$4) RETURNING *`,
      [orgId, title, startsAt, endsAt],
    );
    return res.rows[0];
  }

  async getContest(contestId: string) {
    const res = await this.db.query('SELECT * FROM contests WHERE id = $1', [contestId]);
    if (!res.rows[0]) throw new NotFoundException('Contest not found');
    return res.rows[0];
  }

  /**
   * Learners only ever see sample test cases; hidden tests and unreleased
   * problem versions never leave the server for non-instructor roles.
   * This is the primary "restricted sensitive fields" guarantee from Stage 4.
   */
  async listProblems(contestId: string, requesterRole: string) {
    const problemsRes = await this.db.query(
      'SELECT * FROM problems WHERE contest_id = $1 ORDER BY created_at',
      [contestId],
    );
    const problems = problemsRes.rows;
    const out: any[] = [];
    for (const p of problems) {
      if (p.is_hidden_from_learners_until && new Date(p.is_hidden_from_learners_until) > new Date()) {
        if (requesterRole !== 'instructor' && requesterRole !== 'admin') continue;
      }
      const testCol = requesterRole === 'instructor' || requesterRole === 'admin' ? '*' : null;
      const tcRes = await this.db.query(
        'SELECT id, input, expected_output, is_sample FROM test_cases WHERE problem_id = $1 AND ($2 OR is_sample = true)',
        [p.id, requesterRole === 'instructor' || requesterRole === 'admin'],
      );
      out.push({ ...p, testCases: tcRes.rows });
    }
    return out;
  }

  async getProblemForJudge(problemId: string) {
    // Full (including hidden) test cases — only ever called server-side by judge-worker.
    const p = await this.db.query('SELECT * FROM problems WHERE id = $1', [problemId]);
    if (!p.rows[0]) throw new NotFoundException('Problem not found');
    const tc = await this.db.query('SELECT * FROM test_cases WHERE problem_id = $1', [problemId]);
    return { ...p.rows[0], testCases: tc.rows };
  }
}
