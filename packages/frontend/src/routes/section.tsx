import { Badge } from "@/components/ui/badge";

type SectionRouteProps = {
  title: string;
};

export function SectionRoute({ title }: SectionRouteProps) {
  return (
    <div className="flex items-center justify-between gap-3">
      <h1 className="text-xl font-semibold">{title}</h1>
      <Badge variant="outline">API pending</Badge>
    </div>
  );
}
