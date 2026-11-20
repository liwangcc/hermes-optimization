# Holographic: configure search by meaning from Hermes Desktop

**Target:** `itpartypattaya/hermes-plugin-holographic` · draft only

## Problem or use case

`hermes memory setup` already asks for Holographic's embedding settings. In Hermes Desktop the same settings are out of reach: the memory provider panel renders its fields from a `config_schema.py` next to the plugin's `__init__.py`, and Holographic doesn't ship one, so the panel is empty for it. A Desktop user has to leave Settings and edit `config.yaml`, or run setup in a terminal, to turn embeddings on or change the model.

## Proposal: settings only

Add a `config_schema.py` for `embeddings` and the ten `embedding_*` keys, plus two forwarding methods so the panel reads and saves the profile being configured through the plugin's existing `save_config`.

- Nothing is written until the user saves. A blank field stays unset, so the plugin's own default applies.
- The API key stays in its environment variable. The panel edits only the variable's name, and a pasted key is refused.
- It needs no new Hermes interface and leaves `requires_hermes` alone. On a Hermes without the panel, the file is never read.
- It does not touch recall, indexing or the after-turn catch-up.

I have this working on 0.30.1 (`76689f9`). On Windows 11, **7 targeted tests** pass: 5 new ones for the schema and the panel's read and save, which fail without the change, and the 2 existing ones for `save_config`. I have not run it on Linux or macOS. I checked the panel through Hermes' route functions, not by clicking through a Desktop window with the catalog plugin installed.

Would you take a small PR for this (5 files, about 200 added lines), or would you rather implement it yourself?
