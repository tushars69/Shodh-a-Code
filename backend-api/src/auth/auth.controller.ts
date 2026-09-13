import { Body, Controller, Post } from '@nestjs/common';
import { AuthService } from './auth.service';

@Controller('auth')
export class AuthController {
  constructor(private auth: AuthService) {}

  @Post('join-contest')
  joinContest(@Body() body: { contestId: string; username: string }) {
    return this.auth.joinContest(body.contestId, body.username);
  }

  @Post('login')
  login(@Body() body: { orgId: string; username: string; password: string }) {
    return this.auth.login(body.orgId, body.username, body.password);
  }
}
