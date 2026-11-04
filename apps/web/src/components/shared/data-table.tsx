"use client";

import { useRouter } from "next/navigation";
import {
  createColumnHelper,
  tableFeatures,
  useTable,
  type ColumnDef,
  type RowData,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { TableSkeleton } from "./states";

/**
 * Core-only TanStack table (v9). Filtering, sorting and paging happen in the API
 * layer (`manual` processing), so this component only owns column definitions
 * and rendering. Features and helpers live at module scope so row models stay
 * stable between renders.
 */
const features = tableFeatures({});
export type CoreFeatures = typeof features;

export function columnHelper<T extends RowData>() {
  return createColumnHelper<CoreFeatures, T>();
}

export type TableColumn<T extends RowData> = ColumnDef<CoreFeatures, T, unknown>;

export interface SortState {
  id: string;
  dir: "asc" | "desc";
}

export interface DataTableProps<T extends RowData> {
  columns: ColumnDef<CoreFeatures, T, unknown>[];
  data: T[];
  getRowId: (row: T) => string;
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  /** Accessible table name, also shown to screen readers as the caption. */
  caption: string;
  /** Singular and plural noun for the footer, for example ["report", "reports"]. */
  noun?: [string, string];
  sort?: SortState;
  onSortChange?: (sort: SortState) => void;
  /** Column id → sort key and the direction a first click should use. */
  sortable?: Record<string, { key: string; firstDir?: "asc" | "desc" }>;
  isLoading?: boolean;
  isFetching?: boolean;
  /** Whole-row navigation. The primary cell should also contain a real link. */
  rowHref?: (row: T) => string;
  empty: React.ReactNode;
  /** Extra classes per column id, usually widths and alignment. */
  columnClassName?: Record<string, string>;
  minWidth?: number;
  skeletonColumns?: number;
}

const INTERACTIVE = "a, button, input, select, textarea, label, [role='button'], [role='menuitem']";

export function DataTable<T extends RowData>({
  columns,
  data,
  getRowId,
  total,
  page,
  pageSize,
  onPageChange,
  caption,
  noun = ["row", "rows"],
  sort,
  onSortChange,
  sortable = {},
  isLoading,
  isFetching,
  rowHref,
  empty,
  columnClassName = {},
  minWidth = 880,
  skeletonColumns,
}: DataTableProps<T>) {
  const router = useRouter();
  const table = useTable({ features, columns, data, getRowId: (row) => getRowId(row) });

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);

  const toggleSort = (columnId: string) => {
    const spec = sortable[columnId];
    if (!spec || !onSortChange) return;
    if (sort?.id === spec.key) onSortChange({ id: spec.key, dir: sort.dir === "asc" ? "desc" : "asc" });
    else onSortChange({ id: spec.key, dir: spec.firstDir ?? "asc" });
  };

  return (
    <div>
      <div className="overflow-x-auto">
        <Table style={{ minWidth }} aria-busy={isFetching || undefined}>
          <caption className="sr-only">{caption}</caption>
          <TableHeader>
            {table.getHeaderGroups().map((group) => (
              <TableRow key={group.id} className="hover:bg-transparent">
                {group.headers.map((header) => {
                  const spec = sortable[header.column.id];
                  const active = !!spec && sort?.id === spec.key;
                  const ariaSort = active ? (sort?.dir === "asc" ? "ascending" : "descending") : spec ? "none" : undefined;
                  return (
                    <TableHead
                      key={header.id}
                      aria-sort={ariaSort}
                      className={cn(
                        "h-11 bg-slate-50/70 px-3 text-[11.5px] font-semibold tracking-[0.06em] whitespace-nowrap text-slate-500 uppercase",
                        columnClassName[header.column.id],
                      )}
                    >
                      {header.isPlaceholder ? null : spec && onSortChange ? (
                        <button
                          type="button"
                          onClick={() => toggleSort(header.column.id)}
                          className="-mx-1 inline-flex items-center gap-1 rounded px-1 py-0.5 uppercase hover:text-slate-900 focus-visible:outline-2"
                        >
                          <table.FlexRender header={header} />
                          {active ? (
                            sort?.dir === "asc" ? (
                              <ArrowUp className="size-3" aria-hidden />
                            ) : (
                              <ArrowDown className="size-3" aria-hidden />
                            )
                          ) : (
                            <ChevronsUpDown className="size-3 opacity-50" aria-hidden />
                          )}
                        </button>
                      ) : (
                        <table.FlexRender header={header} />
                      )}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          {!isLoading ? (
            <TableBody className={cn(isFetching && "opacity-60 transition-opacity")}>
              {table.getRowModel().rows.map((row) => {
                const href = rowHref?.(row.original);
                return (
                  <TableRow
                    key={row.id}
                    className={cn("align-top", href && "cursor-pointer hover:bg-slate-50")}
                    onClick={
                      href
                        ? (event) => {
                            if ((event.target as HTMLElement).closest(INTERACTIVE)) return;
                            router.push(href);
                          }
                        : undefined
                    }
                  >
                    {row.getAllCells().map((cell) => (
                      <TableCell
                        key={cell.id}
                        className={cn("px-3 py-3.5 whitespace-normal", columnClassName[cell.column.id])}
                      >
                        <table.FlexRender cell={cell} />
                      </TableCell>
                    ))}
                  </TableRow>
                );
              })}
            </TableBody>
          ) : null}
        </Table>
      </div>

      {isLoading ? <TableSkeleton cols={skeletonColumns ?? columns.length} rows={Math.min(pageSize, 6)} /> : null}
      {!isLoading && data.length === 0 ? <div className="border-t">{empty}</div> : null}

      {!isLoading && total > 0 ? (
        <nav
          aria-label={`${caption} pagination`}
          className="flex flex-wrap items-center justify-between gap-3 border-t px-4 py-3 text-sm text-slate-600"
        >
          <p className="tnum">
            Showing {from}–{to} of {total} {total === 1 ? noun[0] : noun[1]}
          </p>
          <div className="flex items-center gap-2">
            <span className="tnum text-xs">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
              aria-label="Previous page"
            >
              <ChevronLeft aria-hidden /> Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
              aria-label="Next page"
            >
              Next <ChevronRight aria-hidden />
            </Button>
          </div>
        </nav>
      ) : null}
    </div>
  );
}
