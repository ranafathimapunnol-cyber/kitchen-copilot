"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { PackagePlus, Plus, ShieldAlert, Trash2, Undo2, Warehouse } from "lucide-react";

import { api } from "@/lib/api/client";
import { fetchAllRecords } from "@/lib/api/list";
import { ENDPOINTS, STOCK_OPENINGS_ENDPOINT, reverseOpeningEndpoint } from "@/lib/api/endpoints";
import { errorMessage, formatDateTime, formatDay, todayISO } from "@/lib/payments";
import {
  canManageOpeningStock,
  type OpeningEntry,
  type OpeningListResponse,
  type OpeningStatus,
} from "@/lib/stock";
import { checkOpening, plainQuantity, type OpeningCheck, type OpeningLineDraft } from "@/lib/stockMath";
import { allowedUnits, type ConversionRecord, type UnitRecord } from "@/lib/units";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import Alert from "@/components/ui/Alert";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, SelectInput, TextArea, TextInput } from "@/components/ui/Field";
import SearchSelect from "@/components/ui/SearchSelect";
import IconButton from "@/components/ui/IconButton";
import Modal from "@/components/ui/Modal";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import SearchInput from "@/components/ui/SearchInput";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

type StatusFilter = "ALL" | OpeningStatus;
type ItemRecord = { id: number; name: string; standard_unit_id: number; is_active: boolean; item_kind?: string | null };
type Master = { items: ItemRecord[]; units: UnitRecord[]; conversions: ConversionRecord[] };

const PAGE_SIZE = 20;

function blankLine(key: number): OpeningLineDraft {
  return { key: String(key), itemId: "", quantity: "", unitId: "", remarks: "" };
}

function RecordOpeningModal({
  open,
  onClose,
  onRecorded,
  itemsWithActiveOpening,
}: {
  open: boolean;
  onClose: () => void;
  onRecorded: (count: number) => void;
  itemsWithActiveOpening: number[];
}) {
  const [master, setMaster] = useState<Master | null>(null);
  const [loadError, setLoadError] = useState("");
  const [effectiveDate, setEffectiveDate] = useState(todayISO());
  const [remarks, setRemarks] = useState("");
  const nextKey = useRef(1);
  const [lines, setLines] = useState<OpeningLineDraft[]>([blankLine(0)]);
  const [showErrors, setShowErrors] = useState(false);
  const [saving, setSaving] = useState(false);
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    if (!open || master) return;
    let active = true;
    Promise.all([
      fetchAllRecords<ItemRecord>(ENDPOINTS.items),
      fetchAllRecords<UnitRecord>(ENDPOINTS.units),
      fetchAllRecords<ConversionRecord>(ENDPOINTS.unitConversions),
    ])
      .then(([items, units, conversions]) => {
        if (!active) return;
        setMaster({
          // Outsourced food never enters stock (Stage 8a); the API refuses it too.
          items: items.rows.filter((row) => row.is_active && row.item_kind !== "OUTSOURCED").sort((a, b) => a.name.localeCompare(b.name)),
          units: units.rows,
          conversions: conversions.rows,
        });
        setLoadError("");
      })
      .catch((err: unknown) => {
        if (active) setLoadError(errorMessage(err, "Unable to load items and units."));
      });
    return () => {
      active = false;
    };
  }, [open, master]);

  const today = todayISO();
  const check: OpeningCheck = checkOpening(effectiveDate, today, lines, itemsWithActiveOpening);
  const usedLines = lines.filter((line) => line.itemId || line.quantity.trim());
  const available = (master?.items ?? []).filter((item) => !itemsWithActiveOpening.includes(item.id));
  const dateError = showErrors && check.form && check.form !== "Add at least one item." ? check.form : undefined;

  function reset() {
    setEffectiveDate(todayISO());
    setRemarks("");
    setLines([blankLine(0)]);
    nextKey.current = 1;
    setShowErrors(false);
    setSubmitError("");
  }

  function update(key: string, patch: Partial<OpeningLineDraft>) {
    setLines((current) => current.map((line) => (line.key === key ? { ...line, ...patch } : line)));
  }

  function addLine() {
    setLines((current) => [...current, blankLine(nextKey.current++)]);
  }

  function removeLine(key: string) {
    setLines((current) => (current.length === 1 ? [blankLine(nextKey.current++)] : current.filter((line) => line.key !== key)));
  }

  async function submit() {
    setShowErrors(true);
    setSubmitError("");
    if (!check.valid) return;
    setSaving(true);
    try {
      await api.post(STOCK_OPENINGS_ENDPOINT, {
        effective_date: effectiveDate,
        remarks: remarks.trim() || null,
        lines: usedLines.map((line) => ({
          item_id: Number(line.itemId),
          quantity: line.quantity.trim(),
          unit_id: Number(line.unitId),
          remarks: line.remarks.trim() || null,
        })),
      });
      onRecorded(usedLines.length);
      reset();
    } catch (err: unknown) {
      setSubmitError(errorMessage(err, "Unable to record opening stock."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => (saving ? undefined : onClose())}
      dismissible={!saving}
      size="xl"
      title="Record opening stock"
      description="The quantity on hand for each item when the ledger starts. Each item gets one opening entry; it is posted as an opening movement at the start of the chosen day."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button icon={<PackagePlus size={16} aria-hidden />} loading={saving} onClick={submit} disabled={!master}>
            Post opening stock{usedLines.length > 1 ? ` (${usedLines.length} items)` : ""}
          </Button>
        </>
      }
    >
      {loadError ? (
        <Alert tone="error" title="Couldn't load items and units">
          {loadError}
        </Alert>
      ) : !master ? (
        <TableSkeleton rows={3} columns={4} />
      ) : (
        <div className="space-y-5">
          {submitError && (
            <Alert tone="error" title="Opening stock was not recorded" onDismiss={() => setSubmitError("")}>
              {submitError}
            </Alert>
          )}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-[12rem_minmax(0,1fr)]">
            <Field
              label="Opening stock as of"
              required
              error={dateError}
              hint="Today or earlier"
            >
              {({ id, describedBy }) => (
                <TextInput
                  id={id}
                  type="date"
                  max={today}
                  aria-describedby={describedBy}
                  value={effectiveDate}
                  onChange={(event) => setEffectiveDate(event.target.value)}
                />
              )}
            </Field>
            <Field label="Remarks for all lines" hint="Optional, e.g. the stock-take this came from">
              {({ id, describedBy }) => (
                <TextInput
                  id={id}
                  maxLength={500}
                  aria-describedby={describedBy}
                  value={remarks}
                  onChange={(event) => setRemarks(event.target.value)}
                />
              )}
            </Field>
          </div>

          {showErrors && check.form === "Add at least one item." && (
            <Alert tone="error">Add at least one item.</Alert>
          )}

          <div className="space-y-3">
            <p className="text-sm font-medium text-slate-700">Items</p>
            {available.length === 0 && (
              <Alert tone="info">Every active item already has opening stock. Reverse an entry to enter it again.</Alert>
            )}
            <ul className="space-y-3">
              {lines.map((line, index) => {
                const errors = showErrors ? check.lines[line.key] : undefined;
                const units = line.itemId ? allowedUnits(master, line.itemId) : [];
                return (
                  <li
                    key={line.key}
                    className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200 p-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.4fr)_auto] sm:items-start"
                  >
                    <Field label={`Item ${index + 1}`} error={errors?.item}>
                      {({ id, describedBy }) => (
                        <SearchSelect
                          id={id}
                          aria-describedby={describedBy}
                          aria-invalid={Boolean(errors?.item)}
                          value={line.itemId}
                          noun="items"
                          placeholder="Choose an item…"
                          options={available.map((item) => ({ value: String(item.id), label: item.name }))}
                          onChange={(value) => {
                            const chosen = master.items.find((item) => String(item.id) === value);
                            update(line.key, {
                              itemId: value,
                              unitId: chosen ? String(chosen.standard_unit_id) : "",
                            });
                          }}
                        />
                      )}
                    </Field>
                    <Field label="Quantity" error={errors?.quantity}>
                      {({ id, describedBy }) => (
                        <TextInput
                          id={id}
                          inputMode="decimal"
                          aria-describedby={describedBy}
                          aria-invalid={Boolean(errors?.quantity)}
                          value={line.quantity}
                          placeholder="0.000"
                          onChange={(event) => update(line.key, { quantity: event.target.value })}
                        />
                      )}
                    </Field>
                    <Field label="Unit" error={errors?.unit}>
                      {({ id, describedBy }) => (
                        <SelectInput
                          id={id}
                          aria-describedby={describedBy}
                          aria-invalid={Boolean(errors?.unit)}
                          value={line.unitId}
                          disabled={!line.itemId}
                          onChange={(event) => update(line.key, { unitId: event.target.value })}
                        >
                          {!line.itemId && <option value="">—</option>}
                          {units.map((unit) => (
                            <option key={unit.id} value={unit.id}>
                              {unit.symbol}
                            </option>
                          ))}
                        </SelectInput>
                      )}
                    </Field>
                    <Field label="Line remarks">
                      {({ id }) => (
                        <TextInput
                          id={id}
                          maxLength={500}
                          value={line.remarks}
                          onChange={(event) => update(line.key, { remarks: event.target.value })}
                        />
                      )}
                    </Field>
                    <div className="flex sm:pt-7">
                      <IconButton
                        label={`Remove item ${index + 1}`}
                        tone="danger"
                        icon={<Trash2 size={16} />}
                        onClick={() => removeLine(line.key)}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
            <Button variant="secondary" size="sm" icon={<Plus size={14} aria-hidden />} onClick={addLine}>
              Add another item
            </Button>
          </div>
          <p className="text-xs text-slate-500">
            Quantities in another unit are converted to the item&rsquo;s standard unit with the conversion in master data,
            and the factor used is kept with the entry. A wrong entry is corrected by reversing it and entering it again.
          </p>
        </div>
      )}
    </Modal>
  );
}

function ReverseModal({
  entry,
  onClose,
  onReversed,
}: {
  entry: OpeningEntry | null;
  onClose: () => void;
  onReversed: (entry: OpeningEntry) => void;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function reverse() {
    if (!entry) return;
    if (reason.trim().length < 3) {
      setError("Give a reason for the reversal (at least 3 characters).");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const updated = await api.post<OpeningEntry>(reverseOpeningEndpoint(entry.id), { reason: reason.trim() });
      setReason("");
      onReversed(updated);
    } catch (err: unknown) {
      setError(errorMessage(err, "Unable to reverse this entry."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={Boolean(entry)}
      onClose={() => (busy ? undefined : onClose())}
      dismissible={!busy}
      size="sm"
      title={entry ? `Reverse opening stock #${entry.id}?` : "Reverse opening stock"}
      description="A reversal movement takes this quantity back out of stock, effective now. The original entry keeps its date and stays in the history; you can then enter the correct opening stock."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Keep entry
          </Button>
          <Button variant="warning" icon={<Undo2 size={16} aria-hidden />} loading={busy} onClick={reverse}>
            Reverse entry
          </Button>
        </>
      }
    >
      {entry && (
        <div className="space-y-4">
          <dl className="grid grid-cols-2 gap-3 rounded-lg bg-slate-50 p-3 text-sm">
            <div>
              <dt className="text-xs text-slate-500">Item</dt>
              <dd className="font-medium text-slate-900">{entry.item_name}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Quantity</dt>
              <dd className="font-medium text-slate-900">
                {plainQuantity(entry.standard_quantity)} {entry.standard_unit_symbol}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">As of</dt>
              <dd className="text-slate-900">{formatDay(entry.effective_date)}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Recorded by</dt>
              <dd className="text-slate-900">{entry.created_by_name ?? "—"}</dd>
            </div>
          </dl>
          {error && (
            <Alert tone="error" title="Not reversed">
              {error}
            </Alert>
          )}
          <Field label="Reason" required>
            {({ id }) => (
              <TextArea
                id={id}
                rows={3}
                maxLength={500}
                data-autofocus
                value={reason}
                placeholder="e.g. Counted 40 kg, typed 400"
                onChange={(event) => setReason(event.target.value)}
              />
            )}
          </Field>
        </div>
      )}
    </Modal>
  );
}

export default function OpeningStockPage() {
  const { role, loading: authLoading } = useAuthorization();
  const toast = useToast();
  const allowed = canManageOpeningStock(role);

  const [status, setStatus] = useState<StatusFilter>("ALL");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [reloadKey, setReloadKey] = useState(0);
  const [data, setData] = useState<OpeningListResponse | null>(null);
  const [error, setError] = useState("");
  const [loadedKey, setLoadedKey] = useState("");
  const [recordOpen, setRecordOpen] = useState(false);
  const [reversing, setReversing] = useState<OpeningEntry | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(search.trim());
      setPage(1);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  const url = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (status !== "ALL") params.set("status", status);
    if (query) params.set("search", query);
    return `${STOCK_OPENINGS_ENDPOINT}?${params}`;
  }, [page, status, query]);
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedKey !== requestKey;

  useEffect(() => {
    if (!allowed) return;
    let active = true;
    api
      .get<OpeningListResponse>(url)
      .then((response) => {
        if (!active) return;
        setData(response);
        setError("");
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load opening stock."));
      })
      .finally(() => {
        if (active) setLoadedKey(requestKey);
      });
    return () => {
      active = false;
    };
  }, [url, requestKey, allowed]);

  if (!authLoading && !allowed) {
    return (
      <Card>
        <EmptyState
          icon={ShieldAlert}
          title="Opening stock is managed by Admins and Kitchen Managers"
          description="Ask an Admin or Kitchen Manager to record or correct opening stock."
        />
      </Card>
    );
  }

  const counts = data?.status_counts;

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Inventory"
        icon={PackagePlus}
        title="Opening stock"
        description="The starting balance of each item, entered once per item by an Admin or Kitchen Manager. A mistake is corrected by reversing the entry, with a reason, and entering it again; reversed entries stay in the history."
        actions={
          <>
            <Link
              href="/dashboard/stock"
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50"
            >
              <Warehouse size={15} aria-hidden />
              Stock balances
            </Link>
            <Button icon={<Plus size={16} aria-hidden />} onClick={() => setRecordOpen(true)} disabled={!data}>
              Record opening stock
            </Button>
          </>
        }
      />

      <Card>
        <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <SegmentedControl<StatusFilter>
            label="Entry status"
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
            options={[
              { value: "ALL", label: "All", count: counts ? counts.ACTIVE + counts.REVERSED : undefined },
              { value: "ACTIVE", label: "Active", count: counts?.ACTIVE },
              { value: "REVERSED", label: "Reversed", count: counts?.REVERSED },
            ]}
          />
          <SearchInput value={search} onChange={setSearch} label="Search by item" placeholder="Search by item…" className="sm:w-72" />
        </div>

        {error && !loading ? (
          <ErrorState title="Couldn't load opening stock" message={error} onRetry={() => setReloadKey((key) => key + 1)} />
        ) : !data ? (
          <TableSkeleton rows={5} columns={6} />
        ) : data.items.length === 0 ? (
          <EmptyState
            icon={PackagePlus}
            title={query || status !== "ALL" ? "No entries match" : "No opening stock recorded yet"}
            description={
              query || status !== "ALL"
                ? "Try another item or status."
                : "Record what is on hand for each item when the ledger starts."
            }
          />
        ) : (
          <div className={loading ? "opacity-60 transition-opacity" : undefined} aria-busy={loading}>
            <Table minWidth="980px">
              <THead>
                <tr>
                  <TH>Item</TH>
                  <TH align="right">Opening stock</TH>
                  <TH>As of</TH>
                  <TH>Status</TH>
                  <TH>Recorded</TH>
                  <TH>Reversal</TH>
                  <TH align="right">
                    <span className="sr-only">Actions</span>
                  </TH>
                </tr>
              </THead>
              <TBody>
                {data.items.map((entry) => (
                  <TR key={entry.id} muted={entry.status === "REVERSED"}>
                    <TD>
                      <Link
                        href={`/dashboard/stock/${entry.item_id}`}
                        className="font-medium text-slate-900 hover:text-brand-700 hover:underline"
                      >
                        {entry.item_name}
                      </Link>
                      <div className="text-xs text-slate-500">Entry #{entry.id}</div>
                    </TD>
                    <TD align="right" className="whitespace-nowrap">
                      <span className="font-semibold text-slate-900">
                        {plainQuantity(entry.standard_quantity)} {entry.standard_unit_symbol}
                      </span>
                      {entry.unit_symbol !== entry.standard_unit_symbol && (
                        <div className="text-xs text-slate-500">
                          entered as {plainQuantity(entry.quantity)} {entry.unit_symbol} × {entry.conversion_factor}
                        </div>
                      )}
                    </TD>
                    <TD className="whitespace-nowrap">{formatDay(entry.effective_date)}</TD>
                    <TD>
                      <Badge tone={entry.status === "ACTIVE" ? "success" : "warning"} dot>
                        {entry.status === "ACTIVE" ? "Active" : "Reversed"}
                      </Badge>
                    </TD>
                    <TD className="whitespace-nowrap">
                      <div>{entry.created_by_name ?? "—"}</div>
                      <div className="text-xs text-slate-500">{formatDateTime(entry.created_at)}</div>
                    </TD>
                    <TD className="max-w-64">
                      {entry.status === "REVERSED" ? (
                        <>
                          <div className="truncate" title={entry.reversal_reason ?? undefined}>
                            &ldquo;{entry.reversal_reason}&rdquo;
                          </div>
                          <div className="text-xs text-slate-500">
                            {entry.reversed_by_name} · {formatDateTime(entry.reversed_at)}
                          </div>
                        </>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </TD>
                    <TD align="right">
                      {entry.status === "ACTIVE" && (
                        <Button
                          size="sm"
                          variant="secondary"
                          icon={<Undo2 size={14} aria-hidden />}
                          onClick={() => setReversing(entry)}
                        >
                          Reverse
                        </Button>
                      )}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <Pagination
              page={data.page}
              pageCount={data.total_pages}
              total={data.total}
              pageSize={data.page_size}
              noun="entries"
              onPageChange={setPage}
            />
          </div>
        )}
      </Card>

      <RecordOpeningModal
        open={recordOpen}
        onClose={() => setRecordOpen(false)}
        itemsWithActiveOpening={data?.items_with_active_opening ?? []}
        onRecorded={(count) => {
          setRecordOpen(false);
          toast.success(`Opening stock recorded for ${count} ${count === 1 ? "item" : "items"}.`);
          setReloadKey((key) => key + 1);
        }}
      />

      <ReverseModal
        // A fresh dialog per entry: a reason typed for one entry and then
        // cancelled never carries over to another.
        key={reversing?.id ?? "closed"}
        entry={reversing}
        onClose={() => setReversing(null)}
        onReversed={(entry) => {
          setReversing(null);
          toast.success(`Opening stock #${entry.id} for ${entry.item_name} reversed.`);
          setReloadKey((key) => key + 1);
        }}
      />
    </div>
  );
}
