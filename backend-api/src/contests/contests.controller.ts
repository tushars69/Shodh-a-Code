import { Body, Controller, Get, Param, Post, UseGuards } from '@nestjs/common';
import { JwtAuthGuard, CurrentUser } from '../common/jwt.guard';
import { Roles, RolesGuard } from '../common/rbac';
import { ContestsService } from './contests.service';

@Controller('contests')
export class ContestsController {
  constructor(private contests: ContestsService) {}

  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('instructor', 'admin')
  @Post()
  create(@CurrentUser() user: any, @Body() body: { title: string; startsAt: string; endsAt: string }) {
    return this.contests.createContest(user.orgId, body.title, body.startsAt, body.endsAt);
  }

  @Get(':id')
  get(@Param('id') id: string) {
    return this.contests.getContest(id);
  }

  @UseGuards(JwtAuthGuard)
  @Get(':id/problems')
  listProblems(@Param('id') id: string, @CurrentUser() user: any) {
    return this.contests.listProblems(id, user.role);
  }
}
