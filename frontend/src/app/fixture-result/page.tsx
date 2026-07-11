import { FixtureResultWorkspace } from "./workspace";

export default async function FixtureResultPage({
  searchParams,
}: {
  searchParams?: Promise<{ case?: string }>;
}) {
  const params = await searchParams;
  if (process.env.NODE_ENV === "production") {
    return <main style={{ padding: 24 }}>Fixture result workspace is disabled in production.</main>;
  }
  return <FixtureResultWorkspace fixtureKey={params?.case ?? "complete"} />;
}
