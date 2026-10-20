import { screen } from '@testing-library/react';
import type userEvent from '@testing-library/user-event';

type User = ReturnType<typeof userEvent.setup>;

/** Opens the boarding-station picker, searches, and picks the named station. */
export async function chooseStation(user: User, name: string, query = name) {
  await user.click(await screen.findByRole('button', { name: /^Change boarding station/ }));
  await user.type(screen.getByRole('combobox', { name: 'Where are you boarding?' }), query);
  await user.click(screen.getByRole('option', { name: new RegExp(`^${name.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')}`) }));
}
