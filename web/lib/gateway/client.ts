import "server-only";

import { readFileSync } from "node:fs";
import path from "node:path";

import { SignJWT } from "jose";

import type { GatewayError, Role } from "./types";

/**
 * Calls the live web gateway. Every request carries a fresh X-Ripple-Session token: HS256, claims sub, role,
 * member and exp, two minutes ahead (the gateway refuses anything over five). The secret comes from GATEWAY_SECRET
 * or from .ripple/gateway.secret beside a local network, and never reaches the browser.
 */
const LIFETIME_SECONDS = 120;

let cachedSecret: Uint8Array | null = null;

function secret(): Uint8Array {
  if (cachedSecret) return cachedSecret;
  const fromEnv = process.env.GATEWAY_SECRET;
  const text =
    fromEnv || readFileSync(path.join(process.cwd(), "..", ".ripple", "gateway.secret"), "ascii").trim();
  cachedSecret = new TextEncoder().encode(text);
  return cachedSecret;
}

export class GatewayFailure extends Error {
  constructor(
    readonly status: number,
    readonly body: GatewayError,
  ) {
    super(body.message);
  }
}

export type Caller = { sub: string; role: Role; member: string | null };

export async function gatewayFetch<T>(caller: Caller, route: string, body?: unknown): Promise<T> {
  const base = process.env.GATEWAY_URL ?? "http://127.0.0.1:8090";
  const token = await new SignJWT({ role: caller.role, member: caller.member })
    .setProtectedHeader({ alg: "HS256", typ: "JWT" })
    .setSubject(caller.sub)
    .setExpirationTime(Math.floor(Date.now() / 1000) + LIFETIME_SECONDS)
    .sign(secret());
  let response: Response;
  try {
    response = await fetch(base + route, {
      method: body === undefined ? "GET" : "POST",
      headers: {
        "X-Ripple-Session": token,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new GatewayFailure(502, {
      error: "upstream_error",
      message: "The Ripple network is not reachable.",
    });
  }
  if (!response.ok) {
    const fallback: GatewayError = {
      error: "upstream_error",
      message: `The gateway answered ${response.status}.`,
    };
    const parsed = (await response.json().catch(() => fallback)) as GatewayError;
    throw new GatewayFailure(response.status, parsed.message ? parsed : fallback);
  }
  return (await response.json()) as T;
}
