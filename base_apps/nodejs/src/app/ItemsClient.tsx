"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Paper,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import {
  IconAlertCircle,
  IconPlus,
  IconRefresh,
  IconTrash,
} from "@tabler/icons-react";
import { getClientConfig } from "@/lib/config";

type Item = {
  id: number;
  name: string;
  description: string | null;
  display_name: string;
};

function apiBase(): string {
  return getClientConfig().pythonApiBaseUrl.replace(/\/$/, "");
}

export default function ItemsClient() {
  const [hello, setHello] = useState<string>("…");
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const form = useForm({
    initialValues: { name: "", description: "" },
    validate: {
      name: (v) => (v.trim().length === 0 ? "name is required" : null),
    },
  });

  const loadHello = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase()}/hello`);
      const text = await res.text();
      try {
        setHello(JSON.parse(text));
      } catch {
        setHello(text);
      }
    } catch (e) {
      setError(`hello failed: ${(e as Error).message}`);
    }
  }, []);

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiBase()}/items`);
      if (!res.ok) throw new Error(`status ${res.status}`);
      setItems((await res.json()) as Item[]);
      setError(null);
    } catch (e) {
      setError(`list failed: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHello();
    loadItems();
  }, [loadHello, loadItems]);

  async function handleCreate(values: { name: string; description: string }) {
    try {
      const res = await fetch(`${apiBase()}/items`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: values.name,
          description: values.description || null,
        }),
      });
      if (!res.ok) throw new Error(`status ${res.status}`);
      form.reset();
      notifications.show({
        title: "Created",
        message: `Added "${values.name}"`,
        color: "azure",
      });
      await loadItems();
    } catch (e) {
      setError(`create failed: ${(e as Error).message}`);
    }
  }

  async function handleDelete(id: number) {
    try {
      const res = await fetch(`${apiBase()}/items/${id}`, { method: "DELETE" });
      if (!res.ok && res.status !== 204) throw new Error(`status ${res.status}`);
      notifications.show({
        title: "Deleted",
        message: `Item #${id} removed`,
        color: "red",
      });
      await loadItems();
    } catch (e) {
      setError(`delete failed: ${(e as Error).message}`);
    }
  }

  return (
    <Stack gap="md">
      <Paper withBorder p="md" radius="md">
        <Group justify="space-between">
          <div>
            <Text size="sm" c="dimmed">
              edge api says
            </Text>
            <Text fw={500}>{hello}</Text>
          </div>
          <Badge variant="light" color="green" size="lg">
            connected
          </Badge>
        </Group>
      </Paper>

      <Card withBorder radius="md" p="md">
        <Title order={4} mb="sm">
          Add item
        </Title>
        <form onSubmit={form.onSubmit(handleCreate)}>
          <Group align="end" wrap="wrap">
            <TextInput
              label="Name"
              placeholder="e.g. widget"
              w={200}
              {...form.getInputProps("name")}
            />
            <TextInput
              label="Description"
              placeholder="optional"
              w={300}
              {...form.getInputProps("description")}
            />
            <Button type="submit" leftSection={<IconPlus size={16} />}>
              Create
            </Button>
          </Group>
        </form>
      </Card>

      {error && (
        <Alert
          icon={<IconAlertCircle size={16} />}
          color="red"
          title="Request failed"
          variant="light"
          withCloseButton
          onClose={() => setError(null)}
        >
          {error}
        </Alert>
      )}

      <Card withBorder radius="md" p="md">
        <Group justify="space-between" mb="sm">
          <Title order={4}>Items</Title>
          <Group gap="xs">
            <Badge variant="light">{items.length} total</Badge>
            <Tooltip label="Reload">
              <ActionIcon
                variant="subtle"
                onClick={loadItems}
                loading={loading}
              >
                <IconRefresh size={18} />
              </ActionIcon>
            </Tooltip>
          </Group>
        </Group>

        {loading && items.length === 0 ? (
          <Group justify="center" py="lg">
            <Loader size="sm" />
          </Group>
        ) : items.length === 0 ? (
          <Text c="dimmed" ta="center" py="lg">
            No items yet — create one above.
          </Text>
        ) : (
          <Table striped highlightOnHover withRowBorders={false} verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={60}>ID</Table.Th>
                <Table.Th>Display name</Table.Th>
                <Table.Th>Description</Table.Th>
                <Table.Th w={60} ta="right">
                  {""}
                </Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {items.map((it) => (
                <Table.Tr key={it.id}>
                  <Table.Td>
                    <Text c="dimmed">#{it.id}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text fw={500}>{it.display_name}</Text>
                    <Text size="xs" c="dimmed">
                      raw: {it.name}
                    </Text>
                  </Table.Td>
                  <Table.Td>{it.description ?? "—"}</Table.Td>
                  <Table.Td ta="right">
                    <Tooltip label="Delete">
                      <ActionIcon
                        color="red"
                        variant="subtle"
                        onClick={() => handleDelete(it.id)}
                      >
                        <IconTrash size={16} />
                      </ActionIcon>
                    </Tooltip>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Card>
    </Stack>
  );
}
