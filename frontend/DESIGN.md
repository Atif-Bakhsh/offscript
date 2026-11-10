# Design direction and Unslop audit

This implementation uses [Unslop](https://heydamir.design/unslop) by **Damir Sokolovsky** ([@heydamir](https://x.com/heydamir)), licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The local skill source is `/Users/social/Downloads/unslop-main/skills/unslop/SKILL.md`. The design guidance has been adapted to OffScript's explicitly requested palette, typefaces, labels, and CTA style.

## Direction

- **Product:** A voice-agent prompt evaluation instrument for engineers testing intent, calendar boundaries, and consent.
- **Character:** Exact, restrained, inspectable.
- **World:** A test bench with transcripts, assertions, and a guarded write boundary.
- **Moments:** The baseline/refined evidence comparison and the calculated benchmark figures.
- **Signature:** Small crosshairs at section boundaries, used with the fixed architectural grid.

The requested [RKIZA reference](https://rkiza.sa/en) informs the neutral architectural rhythm and white divided-arrow controls. OffScript's actual evidence is the visual material; no decorative illustrations or invented telemetry are needed.

## Original mockup audit

- `demo_preview.html` imported an Arabic typeface despite the English-only requirement.
- Its `.status-dot` used a colored glow; this competes with meaningful outcome colors.
- `.nav-meta` used the dim token for functional data, making important metadata difficult to read.
- The static document could not demonstrate actual request errors, consent outcomes, session isolation, or provenance.

The existing palette and the grid were deliberate user requirements and were retained. This is a new functional application following that direction, not a restyling of another product.

## Applied passes

1. **Spacing:** Use a 4px rhythm, consistent scenario cards, equal arena columns, and larger gaps between sections than within evidence groups.
2. **Color:** Keep chrome neutral. Red means failed or rejected, green means passed or committed, and yellow means a pending gate. Depth comes from surfaces and borders.
3. **Icons:** Avoid decorative icon sets and emoji. Simple textual marks accompany explicit status labels and the requested arrow action.
4. **Copy:** Name the actual caller and test context. Describe replay as curated fixtures, live results as measured outcomes, and commits as mock mutations.
5. **Type:** Keep Plus Jakarta Sans for the interface and JetBrains Mono for technical content. Preserve the user's specified section indices and button weights; use readable functional metadata and system fallbacks.
6. **Layout:** Keep the full workflow in one page. Stack the comparison on smaller screens and contain wide data within local scroll regions.
7. **Details:** Align evidence rows, give controls distinct focus states, and separate reported agent state from actual mutation status.
8. **Visuals:** Let real transcripts, semantic outcomes, and calculated metrics carry the visual emphasis. No generated images or placeholder charts.
9. **Motion:** Limit transitions to control feedback. No pulsing status lights, moving decorations, or looping loaders; honor reduced-motion preferences.

The skill's generic recommendations for sentence-case indices, different fonts, and lighter button weights yield to the user's explicit OffScript requirements. No story video was requested.
