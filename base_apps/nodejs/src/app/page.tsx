import {
  Anchor,
  Badge,
  Container,
  Group,
  List,
  ListItem,
  Paper,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import {
  IconActivity,
  IconBrandAzure,
  IconCheck,
} from "@tabler/icons-react";
import ItemsClient from "./ItemsClient";

export default function HomePage() {
  return (
    <Container size="md" py="xl">
      <Stack gap="lg">
        <Group gap="sm" align="center">
          <ThemeIcon size={42} radius="md" variant="light" color="azure">
            <IconBrandAzure size={26} />
          </ThemeIcon>
          <div>
            <Title order={2}>Azure Observability — Sketch Apps</Title>
            <Text c="dimmed">
              Three small services to practice logs, metrics and distributed
              tracing on Azure Kubernetes Service.
            </Text>
          </div>
        </Group>

        <Paper withBorder p="md" radius="md">
          <Group gap="xs" mb="xs">
            <ThemeIcon variant="light" color="azure" size="sm">
              <IconActivity size={14} />
            </ThemeIcon>
            <Text fw={600}>Architecture</Text>
            <Badge variant="light" color="azure">
              Browser → Next.js → FastAPI → Spring Boot → SQLite
            </Badge>
          </Group>
          <List
            spacing={4}
            size="sm"
            icon={
              <ThemeIcon color="azure" size={16} radius="xl">
                <IconCheck size={10} />
              </ThemeIcon>
            }
          >
            <ListItem>
              <b>Next.js (this app)</b> — SPA shell, calls the FastAPI edge
              directly from the browser.
            </ListItem>
            <ListItem>
              <b>FastAPI</b> — light-weight proxy over the Spring Boot CRUD,
              adds a derived <code>display_name</code>.
            </ListItem>
            <ListItem>
              <b>Spring Boot + embedded SQLite</b> — source of truth for items.
            </ListItem>
          </List>
          <Text size="xs" c="dimmed" mt="sm">
            Backend URL is injected at runtime via{" "}
            <Anchor href="/config.js" target="_blank" rel="noreferrer">
              /config.js
            </Anchor>{" "}
            so the same image works across AKS environments.
          </Text>
        </Paper>

        <ItemsClient />
      </Stack>
    </Container>
  );
}
