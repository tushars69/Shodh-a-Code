import {
  ForbiddenException,
  Inject,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { Pool } from 'pg';
import Redis from 'ioredis';
import { PG_POOL } from '../db/db.module';
import { REDIS_CLIENT, SUBMISSION_QUEUE_KEY } from '../queue/queue.module';

@Injectable()
export class SubmissionsService {
  constructor(
    @Inject(PG_POOL) private db: Pool,
    @Inject(REDIS_CLIENT) private redis: Redis,
  ) {}

  /**
   * Idempotent create: (user_id, problem_id, client_submission_key) is unique.
   * A retried request (e.g. after a flaky network on the client) re-returns the
   * existing row instead of creating a duplicate judge job — this is the
   * "protection against duplicate processing" requirement from Stage 4.
   */
  async create(userId: string, contestId: string, problemId: string, language: string, sourceCode: string, clientKey: string) {
    const existing = await this.db.query(
      'SELECT * FROM submissions WHERE user_id=$1 AND problem_id=$2 AND client_submission_key=$3',
      [userId, problemId, clientKey],
    );
    if (existing.rows[0]) return existing.rows[0];

    const insert = await this.db.query(
      `INSERT INTO submissions (problem_id, user_id, contest_id, language, source_code, client_submission_key)
       VALUES ($1,$2,$3,$4,$5,$6) RETURNING *`,
      [problemId, userId, contestId, language, sourceCode, clientKey],
    );
    const submission = insert.rows[0];

    // Push a lightweight job pointer (not the source itself) onto the queue.
    // The worker re-reads the row from Postgres, so Postgres stays the single
    // source of truth even if the queue is lost/replayed.
    await this.redis.lpush(SUBMISSION_QUEUE_KEY, JSON.stringify({ submissionId: submission.id }));

    return submission;
  }

  async getForUser(submissionId: string, requesterId: string, requesterRole: string) {
    const res = await this.db.query('SELECT * FROM submissions WHERE id = $1', [submissionId]);
    const submission = res.rows[0];
    if (!submission) throw new NotFoundException('Submission not found');

    const isOwner = submission.user_id === requesterId;
    const isStaff = requesterRole === 'instructor' || requesterRole === 'admin';
    if (!isOwner && !isStaff) {
      // This branch is the unauthorized-access case Stage 4 asks us to verify:
      // a learner may never read another learner's private submission/source.
      throw new ForbiddenException("Cannot view another learner's submission");
    }
    if (!isStaff) {
      const { source_code, ...safe } = submission;
      return { ...safe, source_code: isOwner ? source_code : undefined };
    }
    return submission;
  }

  async listForContest(contestId: string, requesterId: string, requesterRole: string) {
    const isStaff = requesterRole === 'instructor' || requesterRole === 'admin';
    const res = await this.db.query(
      isStaff
        ? 'SELECT * FROM submissions WHERE contest_id = $1 ORDER BY submitted_at DESC'
        : 'SELECT id, problem_id, language, status, verdict, score, submitted_at, judged_at FROM submissions WHERE contest_id = $1 AND user_id = $2 ORDER BY submitted_at DESC',
      isStaff ? [contestId] : [contestId, requesterId],
    );
    return res.rows;
  }
}
