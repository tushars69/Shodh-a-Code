import { Controller, Get, Headers, Param, UnauthorizedException } from '@nestjs/common';
import { ContestsService } from '../contests/contests.service';

@Controller('internal/problems')
export class InternalProblemsController {
  constructor(private contests: ContestsService) {}

  @Get(':id')
  get(@Param('id') id: string, @Headers('x-internal-token') token: string) {
    if (!token || token !== process.env.JUDGE_INTERNAL_TOKEN) {
      throw new UnauthorizedException('Invalid internal token');
    }
    return this.contests.getProblemForJudge(id);
  }
}
