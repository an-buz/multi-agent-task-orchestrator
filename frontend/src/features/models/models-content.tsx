"use client";

import Link from "next/link";
import { Cpu, Info } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  CardAction,
} from "@/components/ui/card";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
  EmptyMedia,
} from "@/components/ui/empty";
import {
  FieldGroup,
  Field,
  FieldContent,
  FieldLabel,
  FieldDescription,
} from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useModelSettings, useModelSwitch } from "./queries";

const providers = [
  { key: "anthropic", name: "Anthropic" },
  { key: "openai", name: "OpenAI" },
  { key: "gemini", name: "Gemini" },
] as const;

export default function ModelsContent() {
  const query = useModelSettings();

  const mutation = useModelSwitch();

  const models = query.data?.items ?? [];

  return (
    <AppShell>
      <section className="min-w-0">
        <header className="flex min-h-20 flex-wrap items-center justify-between gap-3 border-b border-border px-6 py-4 lg:px-8">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Models</h1>
            <p className="mt-1 text-xs text-muted-foreground">
              Choose which models your agents can use.
            </p>
          </div>
          <Badge variant="secondary">
            {models.filter((model) => model.enabled).length} enabled
          </Badge>
        </header>
        <div className="mx-auto flex max-w-5xl flex-col gap-6 p-6 lg:p-10">
          <Alert>
            <Info />
            <AlertTitle>Model availability applies across your workspace</AlertTitle>
            <AlertDescription>
              Disabling a model makes its agents unavailable until you save them with an enabled
              model. Active steps finish before runs pause. Runs resume automatically after
              reconfiguration. <Link href="/agents">Manage agents</Link>.
            </AlertDescription>
          </Alert>
          {query.isPending && <Skeleton className="h-52 w-full" aria-label="Loading models" />}
          {query.isError && (
            <Alert variant="destructive">
              <AlertTitle>Could not load models</AlertTitle>
              <AlertDescription>
                {query.error.message}{" "}
                <Button variant="outline" onClick={() => void query.refetch()}>
                  Retry
                </Button>
              </AlertDescription>
            </Alert>
          )}
          {mutation.isError && (
            <Alert variant="destructive">
              <AlertTitle>Could not update model</AlertTitle>
              <AlertDescription>{mutation.error.message}</AlertDescription>
            </Alert>
          )}
          {Object.entries(query.data?.discovery_errors ?? {}).map(([provider, message]) => (
            <Alert key={provider} variant="destructive">
              <AlertTitle>Could not fetch {provider} models</AlertTitle>
              <AlertDescription>{message}</AlertDescription>
            </Alert>
          ))}
          {query.isSuccess &&
            models.length === 0 &&
            !Object.keys(query.data.discovery_errors ?? {}).length && (
              <Empty>
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <Cpu />
                  </EmptyMedia>
                  <EmptyTitle>No available models</EmptyTitle>
                  <EmptyDescription>
                    Configure an Anthropic, OpenAI, or Gemini API key on the server to manage its
                    models.
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
            )}
          {providers.map((provider) => {
            const items = models
              .filter((model) => model.provider === provider.key)
              .sort((first, second) => Number(second.enabled) - Number(first.enabled));

            if (!items.length) return null;

            return (
              <Card key={provider.key}>
                <CardHeader>
                  <CardTitle>
                    <h2>{provider.name} provider</h2>
                  </CardTitle>
                  <CardDescription>Available models from the provider catalogue.</CardDescription>
                  <CardAction>
                    <Badge variant="outline">
                      {items.filter((model) => model.enabled).length} / {items.length} enabled
                    </Badge>
                  </CardAction>
                </CardHeader>
                <CardContent
                  className="model-catalogue-scroll max-h-96 overflow-y-auto"
                  role="region"
                  aria-label={`${provider.name} models`}
                  tabIndex={0}
                >
                  <FieldGroup>
                    {items.map((model) => (
                      <Field
                        key={model.key}
                        orientation="horizontal"
                        data-disabled={mutation.isPending}
                      >
                        <FieldContent>
                          <FieldLabel htmlFor={`model-${model.key}`}>{model.model_id}</FieldLabel>
                          <FieldDescription id={`model-info-${model.key}`}>
                            {model.context_window === null
                              ? "Context limit not reported"
                              : `${model.context_window.toLocaleString()} context tokens`}{" "}
                            · {model.enabled ? "Enabled" : "Disabled"}
                          </FieldDescription>
                        </FieldContent>
                        <Switch
                          id={`model-${model.key}`}
                          checked={model.enabled}
                          disabled={mutation.isPending}
                          aria-describedby={`model-info-${model.key}`}
                          onCheckedChange={(enabled) =>
                            mutation.mutate({ key: model.key, enabled })
                          }
                        />
                      </Field>
                    ))}
                  </FieldGroup>
                </CardContent>
                <CardFooter>
                  <p className="text-xs text-muted-foreground">Changes are saved automatically.</p>
                </CardFooter>
              </Card>
            );
          })}
        </div>
      </section>
    </AppShell>
  );
}
