import { Global, Module } from '@nestjs/common';
import Redis from 'ioredis';

export const REDIS_CLIENT = 'REDIS_CLIENT';
export const SUBMISSION_QUEUE_KEY = 'submissions:queue';

@Global()
@Module({
  providers: [
    {
      provide: REDIS_CLIENT,
      useFactory: () => new Redis(process.env.REDIS_URL as string),
    },
  ],
  exports: [REDIS_CLIENT],
})
export class QueueModule {}
