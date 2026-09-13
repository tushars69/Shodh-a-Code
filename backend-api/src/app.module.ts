import { Module } from '@nestjs/common';
import { DbModule } from './db/db.module';
import { QueueModule } from './queue/queue.module';
import { AuthModule } from './auth/auth.module';
import { ContestsController } from './contests/contests.controller';
import { ContestsService } from './contests/contests.service';
import { SubmissionsController } from './submissions/submissions.controller';
import { SubmissionsService } from './submissions/submissions.service';
import { InternalSubmissionsController } from './submissions/internal.controller';
import { InternalProblemsController } from './submissions/internal-problems.controller';
import { LeaderboardController } from './leaderboard/leaderboard.controller';

@Module({
  imports: [DbModule, QueueModule, AuthModule],
  controllers: [
    ContestsController,
    SubmissionsController,
    InternalSubmissionsController,
    InternalProblemsController,
    LeaderboardController,
  ],
  providers: [ContestsService, SubmissionsService],
})
export class AppModule {}
