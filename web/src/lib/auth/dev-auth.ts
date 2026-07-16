/**
 * Dev-grade auth constants — the SINGLE seam to swap for real auth later.
 *
 * Per the locked architecture the web app is a pure thin client: it holds no
 * credentials logic beyond attaching `Authorization` + `X-Account-Id`. In dev
 * the bearer token *is* the seeded user's UUID (see STATUS.md §3). When real
 * auth (JWT/session) lands, only this module + `AccountProvider` change; every
 * request already flows through `authHeaders()`.
 *
 * Values are overridable via `NEXT_PUBLIC_*` env so a different seed/account
 * doesn't require a code edit. These are non-secret dev identifiers.
 */

export type AccountKind = "personal" | "company";

export interface AccountOption {
  kind: AccountKind;
  id: string;
  label: string;
}

/** Dev user UUID used as the bearer token — set NEXT_PUBLIC_DEV_BEARER in
 * web/.env.local to the UUID `python -m scripts.seed` prints. */
export const DEV_BEARER_TOKEN = process.env.NEXT_PUBLIC_DEV_BEARER ?? "";

/** The two accounts the dev user belongs to; X-Account-Id disambiguates. */
export const ACCOUNTS: AccountOption[] = [
  {
    kind: "personal",
    id: process.env.NEXT_PUBLIC_PERSONAL_ACCOUNT_ID ?? "",
    label: "Personal",
  },
  {
    kind: "company",
    id: process.env.NEXT_PUBLIC_COMPANY_ACCOUNT_ID ?? "",
    label: "Company",
  },
];

if (typeof window !== "undefined" && !DEV_BEARER_TOKEN) {
  // Surfaced once at startup so a fresh clone isn't a silent wall of 401s.
  console.warn(
    "[filemindr] Dev auth is not configured. Copy web/.env.local.example to " +
      "web/.env.local and fill in the UUIDs printed by `python -m scripts.seed`.",
  );
}

export const DEFAULT_ACCOUNT = ACCOUNTS[0];

/**
 * The request headers that authenticate + scope every API call.
 * `accountId` comes from the active account in `AccountProvider`.
 */
export function authHeaders(accountId: string): Record<string, string> {
  return {
    Authorization: `Bearer ${DEV_BEARER_TOKEN}`,
    "X-Account-Id": accountId,
  };
}
