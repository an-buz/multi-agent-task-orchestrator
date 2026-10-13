import RunDetailContent from "@/features/runs/run-detail-content";

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <RunDetailContent id={id} />;
}
