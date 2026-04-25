// Minimal type declarations for the experimental `node:sqlite` builtin
// (Node 22+). Drop this shim once @types/node is bumped to ^22.

declare module "node:sqlite" {
  export interface DatabaseSyncOptions {
    open?: boolean;
    readOnly?: boolean;
    enableForeignKeyConstraints?: boolean;
    enableDoubleQuotedStringLiterals?: boolean;
  }

  export type SQLiteValue = string | number | bigint | Buffer | null;

  export interface StatementSync {
    all(...params: SQLiteValue[]): unknown[];
    get(...params: SQLiteValue[]): unknown;
    run(...params: SQLiteValue[]): { changes: number; lastInsertRowid: number | bigint };
    iterate(...params: SQLiteValue[]): IterableIterator<unknown>;
  }

  export class DatabaseSync {
    constructor(filename: string, options?: DatabaseSyncOptions);
    prepare(sql: string): StatementSync;
    exec(sql: string): void;
    close(): void;
    open(): void;
  }
}
