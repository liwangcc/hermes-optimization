"""Desktop settings of holographic-semantic: the wrapper's own keys. The base provider's keys (scope, search by
meaning through an API, …) stay in config.yaml plugins.hermes-memory-store and `hermes memory setup`.

Hermes reads this file from disk and never imports it as a package: it may import only the pure-data module below.
"""

from plugins.memory.config_schema import (
    KIND_BOOL,
    KIND_TEXT,
    STORAGE_PROVIDER,
    ProviderConfigSchema,
    ProviderField,
)

CONFIG_SCHEMA = ProviderConfigSchema(
    name="holographic-semantic",
    label="Holographic + semantic recall",
    storage=STORAGE_PROVIDER,  # the same config.yaml section the base provider reads (read/write_config_fields)
    # Every field is inline, each under the switch it belongs to: a first-time user sees all of them on one page,
    # with nothing behind "Full config…". Numbers are text fields: the Desktop's number input changes under the mouse
    # wheel and this panel saves on blur, so scrolling the page could change one. settings.to_store checks them.
    fields=(
        ProviderField(
            "semantic_enabled", "Semantic recall", KIND_BOOL, default="false", inline=True,
            description="Before a turn, add facts close in meaning to the message from the local embedding sidecar. "
                        "Nothing leaves this machine; while the sidecar is down, recall stays by words. "
                        "Applies from the next session."),
        ProviderField(
            "semantic_url", "Sidecar address", KIND_TEXT, default="http://127.0.0.1:8791", inline=True,
            description="The local bge-m3 sidecar (memory/sidecar). Index the facts already stored with the job below."),
        ProviderField(
            "semantic_tau", "Similarity threshold", KIND_TEXT, default="0.55", inline=True,
            description="Cosine similarity (0-1) a fact needs to be added by meaning."),
        ProviderField(
            "semantic_max_extra", "Facts added by meaning", KIND_TEXT, default="3", inline=True,
            description="At most this many facts per turn beyond the word search."),
        ProviderField(
            "catalog_enabled", "Fact catalog", KIND_BOOL, default="false", inline=True,
            description="List every recallable fact as #id=label in the system prompt; the agent reads one in full "
                        "with fact_store get. MEMORY.md can stay on beside it. Applies from the next session."),
        ProviderField(
            "catalog_max_tokens", "Catalog budget", KIND_TEXT, default="3000", inline=True,
            description="Estimated tokens the catalog may take; past it the lowest-trust facts are left out."),
    ),
)
