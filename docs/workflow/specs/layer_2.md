# Layer 2 — Cleaning

**Modules:** `src/cleaner.py` (cleaning), `src/structure.py` (sectioning + chunking)

## Purpose

Turn the raw page text into clean, continuous prose, then split it into the sections and overlapping
chunks the later layers work over.

## Cleaning (`cleaner.py`)

- **De-hyphenates** words split across line wraps.
- **Strips repeating headers/footers** and page furniture (detected by finding lines that recur across
  pages, after normalising a leading page number so `42 / Foo` and `33 / Foo` collapse together).
- **Normalises archaic spellings** so older orthography matches modern forms.
- **Fixes whitespace** into continuous text.

## Sectioning and chunking (`structure.py`)

1. **Sectioning.** Splits the cleaned text into logical sections by detecting headings. The detector
   knows common **English and Dutch** report headings (e.g. *introduction / inleiding*,
   *pottery / aardewerk*, *dating / datering*, *finds / vondsten*) and **numbered headings** (`1.`,
   `2.1.`, `1.2.3.`), with guards so decimals like `2.0` aren't mistaken for headings.
2. **Chunking.** Breaks each section into overlapping character chunks of `CHUNK_SIZE` with
   `CHUNK_OVERLAP`, so a term near a chunk edge still has context on both sides. Chunks bound the
   context window used by detection and the AI layers.

## Input → output

- **In:** the raw per-page text from [Layer 1](layer_1.md).
- **Out:** cleaned text split into sections and overlapping chunks.

## Configuration (`config.py`)

| Setting | Role |
|---|---|
| `CHUNK_SIZE` | Chunk length in characters |
| `CHUNK_OVERLAP` | Overlap between consecutive chunks |
