# Design System Strategy: The Modern Chronicle

## 1. Overview & Creative North Star
The Creative North Star for this design system is **"The Modern Chronicle."** This identity moves away from the sterile, plastic nature of typical productivity apps and instead leans into the tactile, grounded feeling of an editorial archival system. It is designed to feel like a digital artifact—authoritative and ancient in spirit, yet sharp and high-performance in execution.

To break the "template" look, we employ **Intentional Asymmetry**. Rather than perfectly centered grids, we utilize generous, uneven whitespace and staggered layouts that guide the eye like a well-composed magazine spread. By layering organic textures and using high-contrast typography scales, we transform a simple tracking tool into a premium, immersive experience.

---

## 2. Colors & Surface Philosophy
The palette is rooted in the earth, utilizing deep forest greens for stability and warm terracotta for momentum.

### The "No-Line" Rule
**Borders are strictly prohibited for sectioning.** To define space, designers must use tonal shifts. A `surface-container-low` section sitting on a `surface` background provides all the definition needed. High-contrast lines are "noise"; we prefer the "silence" of color-blocking.

### Surface Hierarchy & Nesting
Treat the UI as a physical desk with stacked sheets of fine paper. 
- **Base Layer:** `surface` (#fcf9f3)
- **Primary Sectioning:** `surface-container-low` (#f6f3ed)
- **Interactive Elevated Cards:** `surface-container-lowest` (#ffffff)
- **Nested Detail Groups:** `surface-container-high` (#ebe8e2)

### The Glass & Gradient Rule
For floating elements (like persistent navigation or modals), use **Glassmorphism**. Apply `surface` with 80% opacity and a `20px` backdrop-blur. 
*Signature Touch:* For primary Call-to-Actions (CTAs), use a subtle linear gradient from `primary` (#163422) to `primary-container` (#2d4b37). This prevents the earthy green from feeling "flat" and adds a jewel-toned depth.

---

## 3. Typography
Our typography is a dialogue between the archival and the contemporary.

*   **The Voice (Headers):** We use **Newsreader**, a classic serif. It brings the "quest" theme to life, evoking the feel of a printed chronicle.
    *   `display-lg` (3.5rem): Used for major milestones.
    *   `headline-md` (1.75rem): Used for quest titles and section headers.
*   **The Engine (Body):** We use **Manrope**, a clean, modern sans-serif. It ensures that even with the "antique" aesthetic, the app remains highly legible and efficient.
    *   `body-md` (0.875rem): The standard for all quest descriptions and metadata.
    *   `label-md` (0.75rem): Used for status tags and micro-copy.

---

## 4. Elevation & Depth
Depth in this system is a result of light and shadow, not lines and boxes.

*   **The Layering Principle:** Always stack from dark to light or vice versa to create natural lift. Place a `surface-container-lowest` card on a `surface-container-low` background to create a "paper on stone" effect.
*   **Ambient Shadows:** When an element must float, use a shadow with a `24px` blur and `4%` opacity. The shadow color should be a tinted version of `on-surface` (#1c1c18) to mimic real-world ambient occlusion.
*   **The "Ghost Border" Fallback:** If a container requires extra definition (e.g., an input field), use `outline-variant` (#c2c8c0) at **15% opacity**. Never use 100% opaque borders.
*   **Radii:** Use the `xl` (0.75rem) radius for primary containers and `md` (0.375rem) for smaller interactive elements like buttons. This creates a soft, organic silhouette.

---

## 5. Components

### Primary Buttons
Large, authoritative, and grounded. 
- **Style:** Background `primary` (#163422), Text `on-primary` (#ffffff).
- **Radius:** `md` (0.375rem).
- **Interaction:** On hover, transition to the `primary-container` gradient for a "glow" effect.

### Quest Cards
- **Structure:** No borders. Use `surface-container-lowest` for the card background. 
- **Spacing:** Use `1.5rem` internal padding to allow the serif typography room to breathe.
- **Visual Marker:** A subtle vertical accent on the left edge using `secondary` (#95482b) to denote high-priority quests.

### Progress Metrics (The "Chronicle" Grid)
- **Style:** Instead of standard bars, use the **Organic Heatmap**. Small squares with `sm` (0.125rem) radii.
- **Coloring:** Empty states use `surface-dim`. Active states scale from `tertiary-fixed` to `primary`.

### Input Fields
- **Style:** `surface-container-highest` background. 
- **Focus State:** Instead of a thick border, use a soft glow (8px blur) of `surface-tint`.

### Action Chips
- **Style:** Pill-shaped (`full` radius). 
- **Color:** `secondary-container` (#fc9a77) with `on-secondary-container` (#763015) text for a warm, terracotta callout.

---

## 6. Do’s and Don’ts

### Do
*   **DO** use normal whitespace to separate groups, matching the `spacing` value of `2`.
*   **DO** mix Newsreader (Serif) and Manrope (Sans) within the same component to create editorial hierarchy.
*   **DO** use backdrop blurs on floating menus to maintain a sense of "place."
*   **DO** use the `secondary` terracotta color sparingly—it is for "fire," "action," and "momentum."

### Don't
*   **DON’T** use pure black (#000000) for text. Always use `on-surface` (#1c1c18) to keep the "ink on paper" feel.
*   **DON’T** use standard 1px borders to separate list items. Use 16px of vertical space or a subtle background shift instead.
*   **DON’T** use harsh, fast animations. Use "natural" easing (Cubic Bezier 0.4, 0, 0.2, 1) to mimic the weight of physical objects.
*   **DON’T** overcrowd the screen. If a view feels busy, increase the background `surface` area.