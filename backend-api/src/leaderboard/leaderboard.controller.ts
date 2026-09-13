import { Controller, Get, Inject, Param } from '@nestjs/common';
import { Pool } from 'pg';
import { PG_POOL } from '../db/db.module';

@Controller('contests/:contestId/leaderboard')
export class LeaderboardController {
  constructor(@Inject(PG_POOL) private db: Pool) {}

  @Get()
  async get(@Param('contestId') contestId: string) {
    // Best score per (user, problem), summed per user — recomputed on read so
    // the leaderboard is always consistent with the latest judged verdicts,
    // never a separately-maintained counter that can drift out of sync.
    const res = await this.db.query(
      `SELECT u.id AS user_id, u.username, SUM(best.score) AS total_score, MAX(best.judged_at) AS last_judged_at
       FROM users u
       JOIN (
         SELECT DISTINCT ON (user_id, problem_id) user_id, problem_id, score, judged_at
         FROM submissions
         WHERE contest_id = $1 AND status = 'completed'
         ORDER BY user_id, problem_id, score DESC, judged_at ASC
       ) best ON best.user_id = u.id
       GROUP BY u.id, u.username
       ORDER BY total_score DESC, last_judged_at ASC`,
      [contestId],
    );
    return res.rows;
  }
}
