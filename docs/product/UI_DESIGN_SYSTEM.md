# UI Design System

- System fonts, white background, black/gray hierarchy.
- Green, amber, and red communicate status only; text and icons repeat meaning.
- Borders organize dense operating information; cards are limited to repeated
  theme units and the evidence drawer.
- Radius is 3-6 px. Controls use Lucide icons where a familiar symbol exists.
- Stable grids and minimum heights prevent status changes from shifting layout.
- Hero type is reserved for Today. Tool and card headings remain compact.
- CSS variables in `web/src/styles.css` are the source of truth.
- Breakpoints: 1050 px for compact navigation and 760 px for mobile layout.

The initial JavaScript budget is 220 kB raw and 75 kB gzip. Status color may
never be the sole state encoding.
