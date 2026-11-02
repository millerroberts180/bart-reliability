import type { ReactNode } from 'react';
import { followViewLink, viewHref, type View } from '../hooks/useView';

/** A real link to another view (it works without JavaScript and in a new tab). */
export function ViewLink({
  view,
  params,
  className,
  children,
  ...rest
}: {
  view: View;
  params?: Record<string, string | null | undefined> | undefined;
  className?: string | undefined;
  children: ReactNode;
  'aria-current'?: 'page' | undefined;
  'aria-describedby'?: string | undefined;
}) {
  return (
    <a href={viewHref(view, params)} className={className} onClick={followViewLink} {...rest}>
      {children}
    </a>
  );
}
