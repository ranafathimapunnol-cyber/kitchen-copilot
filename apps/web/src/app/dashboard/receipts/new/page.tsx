"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, FileText, PackageCheck, PackagePlus, Save } from "lucide-react";

import { api } from "@/lib/api/client";
import {
  RECEIVABLE_BILLS_ENDPOINT,
  billReceiptsEndpoint,
  billReceivingEndpoint,
} from "@/lib/api/endpoints";
import { errorMessage, formatDay, todayISO } from "@/lib/payments";
import { checkReceipt, fromMilli, toMilli, type LineInput } from "@/lib/receiptMath";
import type { Page } from "@/lib/payments";
import type { ReceivableBill, Receipt, Receiving } from "@/lib/receipts";
import ReceiptLinesEditor, { type EditorLine } from "@/components/receipts/ReceiptLinesEditor";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Field, TextArea, TextInput } from "@/components/ui/Field";
import PageHeader from "@/components/ui/PageHeader";
import SearchInput from "@/components/ui/SearchInput";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

const EMPTY: LineInput = { received: "", accepted: "", rejected: "" };

/** "6.5" → "6.500"; blank → "0.000". */
function exact(text: string): string {
  return fromMilli(toMilli(text) ?? 0);
}

function BillPicker({ onPick }: { onPick: (purchaseId: number) => void }) {
  const [search, setSearch] = useState("");
  const [data, setData] = useState<Page<ReceivableBill> | null>(null);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams({ page_size: "50" });
    if (search.trim()) params.set("search", search.trim());
    const timer = setTimeout(() => {
      api
        .get<Page<ReceivableBill>>(`${RECEIVABLE_BILLS_ENDPOINT}?${params}`)
        .then((response) => {
          if (!active) return;
          setData(response);
          setError("");
        })
        .catch((err: unknown) => {
          if (active) setError(errorMessage(err, "Unable to load bills."));
        });
    }, 250);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [search, reloadKey]);

  return (
    <Card>
      <CardHeader
        title="Which bill is this delivery for?"
        subtitle="Bills with quantities still to receive. Search by invoice number or supplier."
        icon={FileText}
      />
      <div className="border-b border-slate-100 px-5 pb-4">
        <SearchInput label="Search bills" value={search} placeholder="Invoice number or supplier" onChange={setSearch} />
      </div>
      {error ? (
        <ErrorState title="Couldn't load bills" message={error} onRetry={() => setReloadKey((key) => key + 1)} />
      ) : !data ? (
        <TableSkeleton rows={4} columns={5} />
      ) : data.items.length === 0 ? (
        <EmptyState
          icon={PackageCheck}
          title={search.trim() ? "No bills match" : "Nothing left to receive"}
          description={
            search.trim()
              ? "Try another invoice number or supplier."
              : "Every billed quantity is already received or held in a draft receipt."
          }
        />
      ) : (
        <Table minWidth="640px">
          <THead>
            <tr>
              <TH>Bill date</TH>
              <TH>Invoice</TH>
              <TH>Supplier</TH>
              <TH align="right">Lines open</TH>
              <TH align="right">
                <span className="sr-only">Choose</span>
              </TH>
            </tr>
          </THead>
          <TBody>
            {data.items.map((bill) => (
              <TR key={bill.purchase_id}>
                <TD className="whitespace-nowrap">{formatDay(bill.purchase_date)}</TD>
                <TD className="whitespace-nowrap font-medium text-slate-900">{bill.invoice_number}</TD>
                <TD>{bill.supplier_name ?? `Supplier #${bill.supplier_id}`}</TD>
                <TD align="right" className="tabular-nums">
                  {bill.open_line_count} of {bill.line_count}
                </TD>
                <TD align="right">
                  <Button size="sm" variant="secondary" onClick={() => onPick(bill.purchase_id)} data-pick-bill={bill.invoice_number}>
                    Receive
                  </Button>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </Card>
  );
}

function NewReceipt() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const toast = useToast();
  const billParam = Number(searchParams.get("bill")) || null;

  const [receiving, setReceiving] = useState<Receiving | null>(null);
  const [loadError, setLoadError] = useState("");
  const [inputs, setInputs] = useState<LineInput[]>([]);
  const [receiptDate, setReceiptDate] = useState(todayISO());
  const [remarks, setRemarks] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [loadedBill, setLoadedBill] = useState<number | null>(null);

  useEffect(() => {
    if (!billParam) return;
    let active = true;
    api
      .get<Receiving>(billReceivingEndpoint(billParam))
      .then((response) => {
        if (!active) return;
        setReceiving(response);
        setInputs(response.lines.map(() => ({ ...EMPTY })));
        setLoadError("");
      })
      .catch((err: unknown) => {
        if (active) setLoadError(errorMessage(err, "Unable to load this bill."));
      })
      .finally(() => {
        if (active) setLoadedBill(billParam);
      });
    return () => {
      active = false;
    };
  }, [billParam]);

  const lines: EditorLine[] = useMemo(
    () =>
      (receiving?.lines ?? []).map((line, index) => ({
        line,
        remaining: line.remaining_quantity,
        input: inputs[index] ?? EMPTY,
      })),
    [receiving, inputs],
  );
  const check = checkReceipt(lines);
  const today = todayISO();
  const dateInvalid = !receiptDate || receiptDate > today;
  const nothingLeft = Boolean(receiving) && lines.every((line) => toMilli(line.remaining) === 0);

  function pickBill(purchaseId: number) {
    router.replace(`/dashboard/receipts/new?bill=${purchaseId}`);
  }

  function save() {
    if (!receiving || !check.canSave || dateInvalid) return;
    setSaving(true);
    setSaveError("");
    const items = lines
      .map(({ line, input }, index) => ({ line, input, included: check.lines[index].included }))
      .filter(({ included }) => included)
      .map(({ line, input }) => ({
        purchase_item_id: line.purchase_item_id,
        quantity_received: exact(input.received),
        quantity_accepted: exact(input.accepted),
        quantity_rejected: exact(input.rejected),
      }));
    api
      .post<Receipt>(billReceiptsEndpoint(receiving.purchase_id), {
        receipt_date: receiptDate,
        remarks: remarks.trim() || null,
        items,
      })
      .then((receipt) => {
        toast.success(`Draft receipt GR-${receipt.id} saved.`);
        router.push(`/dashboard/receipts/${receipt.id}`);
      })
      .catch((err: unknown) => {
        setSaveError(errorMessage(err, "The receipt could not be saved."));
        setSaving(false);
      });
  }

  const loading = Boolean(billParam) && loadedBill !== billParam;

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Purchasing"
        icon={PackagePlus}
        title="New goods receipt"
        description="Record what arrived against the supplier's bill. Saving creates a draft: it holds the quantity but does not change stock until the receipt is accepted."
        actions={
          <Link
            href="/dashboard/receipts"
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50"
          >
            <ArrowLeft size={15} aria-hidden />
            All receipts
          </Link>
        }
      />

      {!billParam ? (
        <BillPicker onPick={pickBill} />
      ) : loading ? (
        <Card>
          <TableSkeleton rows={4} columns={8} />
        </Card>
      ) : loadError || !receiving ? (
        <Card>
          <ErrorState
            title="Couldn't open this bill"
            message={loadError || "This bill was not found."}
            onRetry={() => router.replace("/dashboard/receipts/new")}
          />
        </Card>
      ) : (
        <>
          <Card>
            <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Bill</p>
                <p className="mt-1 text-lg font-semibold text-slate-900" data-receipt-bill>
                  {receiving.invoice_number}
                </p>
                <p className="text-sm text-slate-600">
                  {receiving.supplier_name ?? `Supplier #${receiving.supplier_id}`} · billed {formatDay(receiving.purchase_date)}
                </p>
              </div>
              <Button variant="secondary" size="sm" onClick={() => router.replace("/dashboard/receipts/new")}>
                Choose another bill
              </Button>
            </div>
            <div className="grid grid-cols-1 gap-4 border-t border-slate-100 p-5 sm:grid-cols-[12rem_minmax(0,1fr)]">
              <Field label="Received on" required error={dateInvalid ? "Choose a date that is not in the future." : undefined}>
                {({ id, describedBy }) => (
                  <TextInput
                    id={id}
                    type="date"
                    max={today}
                    value={receiptDate}
                    aria-describedby={describedBy}
                    aria-invalid={dateInvalid}
                    onChange={(event) => setReceiptDate(event.target.value)}
                  />
                )}
              </Field>
              <Field label="Remarks" hint="Optional: vehicle, delivery note number, condition.">
                {({ id, describedBy }) => (
                  <TextArea
                    id={id}
                    rows={1}
                    maxLength={1000}
                    aria-describedby={describedBy}
                    value={remarks}
                    onChange={(event) => setRemarks(event.target.value)}
                  />
                )}
              </Field>
            </div>
          </Card>

          {(receiving.outsourced_lines?.length ?? 0) > 0 && (
            <Alert tone="info" title="Outsourced food on this bill">
              {receiving.outsourced_lines!.map((line) => line.item_name).join(", ")}{" "}
              {receiving.outsourced_lines!.length === 1 ? "is" : "are"} outsourced food: received as an outsourced delivery under
              Outsourced Food, never into ingredient stock, so {receiving.outsourced_lines!.length === 1 ? "it is" : "they are"} not listed here.
            </Alert>
          )}

          <Card>
            <CardHeader
              title="Quantities"
              subtitle="Enter what arrived now. Split it into accepted and rejected before the receipt is accepted; only accepted quantities enter stock."
              icon={PackageCheck}
            />
            {nothingLeft ? (
              <EmptyState
                icon={PackageCheck}
                title="Nothing left to receive on this bill"
                description="Every billed quantity is already received or held in a draft receipt."
              />
            ) : (
              <ReceiptLinesEditor
                lines={lines}
                checks={check.lines}
                disabled={saving}
                onChange={(index, input) =>
                  setInputs((current) => current.map((value, i) => (i === index ? input : value)))
                }
              />
            )}
          </Card>

          {saveError && (
            <Alert tone="error" title="Not saved">
              {saveError}
            </Alert>
          )}
          {check.canSave && !check.allClassified && (
            <Alert tone="info">
              Some received quantities are not yet split into accepted and rejected. You can save the draft now and
              complete the split before accepting it.
            </Alert>
          )}

          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <Link
              href="/dashboard/receipts"
              className="inline-flex h-10 items-center justify-center rounded-lg px-4 text-sm font-medium text-slate-600 hover:bg-slate-100"
            >
              Cancel
            </Link>
            <Button
              icon={<Save size={15} aria-hidden />}
              loading={saving}
              disabled={!check.canSave || dateInvalid || nothingLeft}
              onClick={save}
            >
              Save draft receipt
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

export default function NewReceiptPage() {
  return (
    <Suspense
      fallback={
        <Card>
          <TableSkeleton rows={4} columns={5} />
        </Card>
      }
    >
      <NewReceipt />
    </Suspense>
  );
}
