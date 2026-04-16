# UI/UX Design & Implementation Standards for Functional Pages

This document defines the standards for developing functional web pages and report screens. Follow these rules strictly during implementation.

## 1. Loading States
- Display "Now Loading" text in the top-left corner before scripts and CSS are fully loaded.
- Use a background layer with an animation (e.g., increasing number of dots "...") to inform the user that the process is ongoing even during delays.

## 2. Layout & Object Sizing
- **Separation of Concerns:** Separate control areas (search filters, registration forms) from display areas (tables, lists, charts).
- **Resolution Independence:** Control areas must be resolution-independent.
- **Size Constraints:**
    - Display areas must have a defined maximum value (Max-width/height) to maintain readability.
    - Every object must have defined Minimum and Maximum values.
    - Enable horizontal scrolling within an object or object group if the content exceeds the maximum width.
- **Positioning:**
    - Place action buttons as close as possible to the related input fields.
    - Avoid overlapping objects.

## 3. Terminology & Localization
- **Units:** Use the format "Name (Unit)". Avoid using expressions like "~ count" or "~ number of".
- **Language Labels:** Display the language name in its native script followed by the ISO code in parentheses. (e.g., English(en), 한국어(ko)).
- **Sorting:** Sort language lists in ascending order based on ISO language codes.
- **Fallback:** Use the browser's language setting as default. If data for that language is unavailable, fall back to English(en).

## 4. Charts & Data Visualization
- **Axis Titles:** Include axis titles whenever possible, following the "Name (Unit)" format.
- **Data Tables:**
    - Provide a data table below every numerical chart.
    - Data tables should be collapsible, with the default state set to "Collapsed".
    - The order of legend items must match the order of columns in the data table.
- **Tooltips:**
    - Align text to the left and numerical values to the right.
    - Limit tooltip size and add a scrollbar if the list is long to prevent it from overflowing the chart area.
- **Empty States:** Use a unified format and text (e.g., "No data to display.") when indicators cannot be rendered.

## 5. Tables & Lists
- **Alignment:**
    - Align numerical data to the right.
    - Align variable-length text to the left.
- **Column Management:**
    - Adjust column widths so content fits in a single line.
    - Use fixed widths if the maximum content length is predictable.
    - For dynamic widths, always set Minimum and Maximum values.
    - Truncate overflowing content with an ellipsis ("...") and provide the full text via a tooltip.
- **Structure:**
    - Use Rows for frequently changing data (e.g., dates/periods).
    - Use Columns for fixed data categories (e.g., legend items).
- **Processed Data (Totals/Averages):**
    - Place processed/calculated values at the far right or at the bottom.
    - Apply a background color to these cells to distinguish them from raw data.

## 6. File Downloads
- **Naming Convention:** Use underscores ("_") to separate identifiers by hierarchy, ending with date/time information.
- **Format:** [Service/Product]_[Category]_[Project]_[Data_Item]_[Period].[Extension]
- **Example:** ServiceName_Category_Project_Data_20240101-20240131.xlsx
