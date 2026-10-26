import '@fontsource-variable/schibsted-grotesk';
import '@fontsource-variable/source-serif-4';
import '@fontsource-variable/jetbrains-mono';
import './styles/tokens.css';
import './styles/base.css';
import './styles/app.css';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
// This build's data mode: src/modes/mock.tsx, http.tsx or static.tsx, chosen by
// VITE_DATA_MODE in vite.config.ts.
import { Site } from '@data-mode';

const root = document.getElementById('root');
if (!root) throw new Error('Missing #root element');

createRoot(root).render(
  <StrictMode>
    <Site />
  </StrictMode>,
);
