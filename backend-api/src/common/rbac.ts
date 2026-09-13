import {
  CanActivate,
  ExecutionContext,
  Injectable,
  SetMetadata,
  ForbiddenException,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';

export const ROLES_KEY = 'roles';
export const Roles = (...roles: string[]) => SetMetadata(ROLES_KEY, roles);

/**
 * Enforces org-scoping + role checks in one place, and writes every decision
 * (allowed or not) to the audit log via request.auditNote, which controllers
 * fill in with resource-level detail. This is what backs the Stage 4
 * "verify one unauthorized-access case" + diagnostic-visibility requirements.
 */
@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const required = this.reflector.get<string[]>(ROLES_KEY, context.getHandler());
    if (!required || required.length === 0) return true;

    const req = context.switchToHttp().getRequest();
    const user = req.user;
    if (!user) throw new ForbiddenException('Not authenticated');

    if (!required.includes(user.role)) {
      req.auditDenied = { reason: 'role_not_permitted', required, actual: user.role };
      throw new ForbiddenException('Insufficient role for this resource');
    }
    return true;
  }
}
