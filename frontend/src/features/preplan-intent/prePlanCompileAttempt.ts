export type PrePlanCompileAttempt = {
  parentIntentRevisionId: string | null;
  idempotencyKey: string;
};

export function resolvePrePlanCompileAttempt(
  current: PrePlanCompileAttempt | null,
  parentIntentRevisionId: string | null,
  startNewAttempt: boolean,
  createKey: () => string,
): PrePlanCompileAttempt {
  if (!startNewAttempt && current?.parentIntentRevisionId === parentIntentRevisionId) {
    return current;
  }
  return { parentIntentRevisionId, idempotencyKey: createKey() };
}
