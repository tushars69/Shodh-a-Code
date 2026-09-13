import { Body, Controller, Get, Param, Post, Query, UseGuards } from '@nestjs/common';
import { JwtAuthGuard, CurrentUser } from '../common/jwt.guard';
import { SubmissionsService } from './submissions.service';

@Controller('submissions')
@UseGuards(JwtAuthGuard)
export class SubmissionsController {
  constructor(private submissions: SubmissionsService) {}

  @Post()
  create(
    @CurrentUser() user: any,
    @Body()
    body: {
      contestId: string;
      problemId: string;
      language: string;
      sourceCode: string;
      clientSubmissionKey: string;
    },
  ) {
    return this.submissions.create(
      user.sub,
      body.contestId,
      body.problemId,
      body.language,
      body.sourceCode,
      body.clientSubmissionKey,
    );
  }

  @Get(':id')
  get(@Param('id') id: string, @CurrentUser() user: any) {
    return this.submissions.getForUser(id, user.sub, user.role);
  }

  @Get()
  list(@Query('contestId') contestId: string, @CurrentUser() user: any) {
    return this.submissions.listForContest(contestId, user.sub, user.role);
  }
}
