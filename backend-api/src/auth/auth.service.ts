import { Inject, Injectable, NotFoundException, UnauthorizedException } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import { Pool } from 'pg';
import * as bcrypt from 'bcryptjs';
import { v4 as uuidv4 } from 'uuid';
import { PG_POOL } from '../db/db.module';

@Injectable()
export class AuthService {
  constructor(
    @Inject(PG_POOL) private db: Pool,
    private jwt: JwtService,
  ) {}

  /**
   * Preserves the original "join with Contest ID and username" learner flow,
   * but backs it with a real (org-scoped) identity: the same username within
   * an org resolves to the same user row across sessions, rather than a
   * throwaway anonymous handle.
   */
  async joinContest(contestId: string, username: string) {
    const contestRes = await this.db.query('SELECT * FROM contests WHERE id = $1', [contestId]);
    const contest = contestRes.rows[0];
    if (!contest) throw new NotFoundException('Contest not found');

    let userRes = await this.db.query(
      'SELECT * FROM users WHERE org_id = $1 AND username = $2',
      [contest.org_id, username],
    );
    let user = userRes.rows[0];

    if (!user) {
      const randomPass = uuidv4();
      const hash = await bcrypt.hash(randomPass, 10);
      const insertRes = await this.db.query(
        `INSERT INTO users (org_id, username, display_name, password_hash, role)
         VALUES ($1, $2, $2, $3, 'learner') RETURNING *`,
        [contest.org_id, username, hash],
      );
      user = insertRes.rows[0];
    }

    const token = await this.signToken(user);
    return { token, user: this.publicUser(user), contest };
  }

  async login(orgId: string, username: string, password: string) {
    const res = await this.db.query('SELECT * FROM users WHERE org_id = $1 AND username = $2', [
      orgId,
      username,
    ]);
    const user = res.rows[0];
    if (!user) throw new UnauthorizedException('Invalid credentials');
    const ok = await bcrypt.compare(password, user.password_hash);
    if (!ok) throw new UnauthorizedException('Invalid credentials');
    const token = await this.signToken(user);
    return { token, user: this.publicUser(user) };
  }

  private async signToken(user: any) {
    return this.jwt.signAsync({
      sub: user.id,
      orgId: user.org_id,
      role: user.role,
      username: user.username,
    });
  }

  private publicUser(user: any) {
    const { password_hash, ...rest } = user;
    return rest;
  }
}
