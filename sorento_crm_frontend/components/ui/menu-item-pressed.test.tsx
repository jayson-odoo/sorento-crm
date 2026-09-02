/**
 * M1-05 - dropdown, context, menubar and command items answer on the way
 * down like every other pressable (S1-09 gave the shared controls this;
 * these four never got it), and a clickable DataGrid row darkens on
 * pointer-down instead of only lifting on hover.
 */
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from './dropdown-menu';
import { ContextMenu, ContextMenuContent, ContextMenuItem, ContextMenuTrigger } from './context-menu';
import { Menubar, MenubarContent, MenubarItem, MenubarMenu, MenubarTrigger } from './menubar';
import { Command, CommandItem, CommandList } from './command';

function classOf(el: Element | null) {
  return el?.getAttribute('class') ?? '';
}

describe('Menu item pressed states (M1-05)', () => {
  it('DropdownMenuItem carries PRESSED_CLASS', async () => {
    render(
      <DropdownMenu>
        <DropdownMenuTrigger>Open menu</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem>Item one</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>,
    );
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Open menu' }), { button: 0 });
    const item = await screen.findByText('Item one');
    expect(classOf(item.closest('[data-slot="dropdown-menu-item"]'))).toContain('active:scale-[0.97]');
  });

  it('ContextMenuItem carries PRESSED_CLASS', () => {
    render(
      <ContextMenu>
        <ContextMenuTrigger>Right-click me</ContextMenuTrigger>
        <ContextMenuContent>
          <ContextMenuItem>Item one</ContextMenuItem>
        </ContextMenuContent>
      </ContextMenu>,
    );
    fireEvent.contextMenu(screen.getByText('Right-click me'));
    const item = screen.getByText('Item one');
    expect(classOf(item.closest('[data-slot="context-menu-item"]'))).toContain('active:scale-[0.97]');
  });

  it('MenubarItem carries PRESSED_CLASS', async () => {
    render(
      <Menubar>
        <MenubarMenu>
          <MenubarTrigger>File</MenubarTrigger>
          <MenubarContent>
            <MenubarItem>New</MenubarItem>
          </MenubarContent>
        </MenubarMenu>
      </Menubar>,
    );
    fireEvent.pointerDown(screen.getByText('File'), { button: 0 });
    const item = await screen.findByText('New');
    expect(classOf(item.closest('[data-slot="menubar-item"]'))).toContain('active:scale-[0.97]');
  });

  it('CommandItem carries PRESSED_CLASS', () => {
    render(
      <Command>
        <CommandList>
          <CommandItem>Result one</CommandItem>
        </CommandList>
      </Command>,
    );
    const item = screen.getByText('Result one');
    expect(classOf(item.closest('[data-slot="command-item"]'))).toContain('active:scale-[0.97]');
  });
});

describe('Clickable DataGrid row darkens on pointer-down (M1-05)', () => {
  // A source assertion is what a render test cannot speak for here without
  // standing up the whole grid + table context.
  const src = fs.readFileSync(path.join(__dirname, 'data-grid-table.tsx'), 'utf8');
  const flat = src.replace(/\s+/g, ' ');

  it('gates active:bg-muted/60 on the row being clickable and not stripped', () => {
    expect(flat).toContain("(href || props.onRowClick) && !props.tableLayout?.stripped && 'active:bg-muted/60'");
  });

  it('leaves the press cue off the skeleton row and off an unclickable row', () => {
    // One occurrence in the file, and the assertion above says which one it is:
    // the unconditional class string that both row builders open with no longer
    // carries it, so a row with no rowHref/onRowClick never darkens.
    expect(src.match(/active:bg-muted\/60/g) ?? []).toHaveLength(1);
    expect(flat).toContain("'hover:bg-muted/40 data-[state=selected]:bg-muted/50'");

    const from = src.indexOf('function DataGridTableBodyRowSkeleton');
    expect(from).toBeGreaterThan(-1);
    const skeleton = src.slice(from, src.indexOf('\n}\n', from));
    expect(skeleton).toContain('hover:bg-muted/40');
    expect(skeleton).not.toContain('active:bg-muted/60');
  });
});
