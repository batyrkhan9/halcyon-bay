/** The gateway refused. `reason` is written for people and is already in the audit log. */
export class Denied extends Error {
  reason: string;
  constructor(reason: string) {
    super(reason);
    this.name = 'Denied';
    this.reason = reason;
  }
}

export class HttpError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'HttpError';
    this.status = status;
  }
}

export class Unreachable extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'Unreachable';
  }
}
