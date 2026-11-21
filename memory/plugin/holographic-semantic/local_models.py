"""The local embedding models the setup can deploy, each pinned to one commit with every file's size and SHA-256, and
where a profile keeps one model's weights and index."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT = "bge-m3"
_LEGACY = Path("services") / "semantic-memory" / "models" / "bge-m3"  # the manual sidecar's own BGE-M3 weights


@dataclass(frozen=True)
class LocalModel:
    id: str  # the job option, the receipt and the service's /health: letters, digits and '-'
    label: str
    repo: str
    rev: str
    dim: int
    files: dict[str, tuple[int, str]]  # name -> (bytes, sha256)
    note: str
    note_zh: str

    @property
    def base(self) -> str:
        return f"https://huggingface.co/{self.repo}/resolve/{self.rev}"

    @property
    def size(self) -> int:
        return sum(size for size, _ in self.files.values())


# No model here needs a query instruction or remote code: the service embeds facts and messages the same way.
MODELS = (
    LocalModel(
        "bge-m3", "BGE-M3", "BAAI/bge-m3", "5617a9f61b028005a4858fdac845db406aefb181", 1024,
        {
            "config_sentence_transformers.json": (123, "1eef72430e7194a1e59680e635aed81ffa083f05668dbc5bb1c56c04c0999c38"),
            "config.json": (687, "26159e7ad065073448460117eb24b7a4572f6f4e78eadff65dc0a11c052449fa"),
            "modules.json": (349, "84e40c8e006c9b1d6c122e02cba9b02458120b5fb0c87b746c41e0207cf642cf"),
            "pytorch_model.bin": (2271145830, "b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38"),
            "sentence_bert_config.json": (54, "eb9b44b13c0f52a3b3685c3b1cbdea1ba8b04bea123b98f61610048940776eb1"),
            "sentencepiece.bpe.model": (5069051, "cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865"),
            "special_tokens_map.json": (964, "8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835"),
            "tokenizer_config.json": (444, "a62b2b6784f990259fddef5f16388693a8043be4f69179e6a5257eeb3f9abac4"),
            "tokenizer.json": (17098108, "21106b6d7dab2952c1d496fb21d5dc9db75c28ed361a05f5020bbba27810dd08"),
            "1_Pooling/config.json": (191, "e54c164a07274f2eb45bb724f54a79d1efcc90c41573887cd9a29aeee0597352"),
        },
        "Multilingual; the largest and most capable of the three, and the default.",
        "多语言，三者中体积最大、能力最强，默认模型。"),
    LocalModel(
        "bge-small-zh", "BGE-small-zh v1.5", "BAAI/bge-small-zh-v1.5", "7999e1d3359715c523056ef9478215996d62a620", 512,
        {
            "config_sentence_transformers.json": (124, "940d5f50db195fa6e5e6a4f122c095f77880de259d74b14a65779ed48bdd7c56"),
            "config.json": (776, "3853a7979202c348751b753e36f579c41d8da7d36af617d3d907e1fc9b441f2a"),
            "modules.json": (349, "84e40c8e006c9b1d6c122e02cba9b02458120b5fb0c87b746c41e0207cf642cf"),
            "model.safetensors": (95827648, "354763b9b1357bc9c44f62c6be2276321081ed2567773608c0d0785b61d5a026"),
            "sentence_bert_config.json": (52, "84e39fda68ccbff05bfa723ae9c0e70e23e2ec373b76e0f8c6e71af72a693cbf"),
            "special_tokens_map.json": (125, "b6d346be366a7d1d48332dbc9fdf3bf8960b5d879522b7799ddba59e76237ee3"),
            "tokenizer_config.json": (367, "e6f3b96db926a37d4039995fbf5ad17de158dfb8f6343d607e4dbaad18d75f5a"),
            "tokenizer.json": (439125, "48cea5d44424912a6fd1ea647bf4fe50b55ab8b1e5879c3275f80e339e8fae26"),
            "vocab.txt": (109540, "45bbac6b341c319adc98a532532882e91a9cefc0329aa57bac9ae761c27b291c"),
            "1_Pooling/config.json": (190, "aaa8861589f80c961a03cc86c7eeaef7605c1676b9ab55329d33a304738769c6"),
        },
        "Chinese only; small and fast.",
        "中文专用，体积小、速度快。"),
    LocalModel(
        "multilingual-minilm", "Multilingual MiniLM-L12 v2", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "e8f8c211226b894fcb81acc59f3b34ba3efd5f42", 384,
        {
            "config_sentence_transformers.json": (122, "b8c64b5cece00d8424b4896ea75b512b6008576088497609dfeb6bd63e6d36b8"),
            "config.json": (645, "6300193cb75e01cf80c96decef7187dfb33094d97cc1490b7ead6ff134476e4e"),
            "modules.json": (229, "8f4b264b80206c830bebbdcae377e137925650a433b689343a63bdc9b3145460"),
            "model.safetensors": (470641600, "eaa086f0ffee582aeb45b36e34cdd1fe2d6de2bef61f8a559a1bbc9bd955917b"),
            "sentence_bert_config.json": (53, "70f4448f31320443fe3557cacea5abf2dcc4915dda8c80646bec9f3bb0aa5a1f"),
            "sentencepiece.bpe.model": (5069051, "cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865"),
            "special_tokens_map.json": (239, "378eb3bf733eb16e65792d7e3fda5b8a4631387ca04d2015199c4d4f22ae554d"),
            "tokenizer_config.json": (526, "5036ea374ffedd706e3bef33e2e0d6953cb868ef8a490e76e32ba0faa37a6b9b"),
            "tokenizer.json": (9081518, "2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8"),
            "1_Pooling/config.json": (190, "4be450dde3b0273bb9787637cfbd28fe04a7ba6ab9d36ac48e92b11e350ffc23"),
        },
        "Multilingual and light; reads only the first 128 tokens of a fact.",
        "多语言轻量模型，每条事实只读取前 128 个 token。"),
)


def find(model_id: str) -> LocalModel | None:
    return next((model for model in MODELS if model.id == model_id), None)


def managed_dir(root: Path, model: LocalModel) -> Path:
    """Where setup downloads *model*: one directory per pinned commit, so another version never mixes in."""
    return root / f"model-{model.rev[:12]}"


def legacy_dir(home: Path, model: LocalModel) -> Path | None:
    return home / _LEGACY if model.id == DEFAULT else None


def index_dir(root: Path, model: LocalModel) -> Path:
    """The service's fact vectors: under the profile (*root*), one index per model and pinned version."""
    return root / "vectors" / f"{model.id}-{model.rev[:12]}"


def _held(directory: Path, model: LocalModel) -> int:
    """Bytes of the model's files already in *directory*, by size alone: quick enough for the settings page.
    Deployment still verifies every SHA-256."""
    total = 0
    for name, (size, _) in model.files.items():
        try:
            if (directory / name).stat().st_size == size:
                total += size
        except OSError:
            continue
    return total


def cache(home: Path, root: Path, model: LocalModel) -> tuple[Path, int]:
    """(where the weights are or will be kept, the bytes of them already there)."""
    legacy = legacy_dir(home, model)
    if legacy is not None and _held(legacy, model) == model.size:
        return legacy, model.size
    target = managed_dir(root, model)
    return target, _held(target, model)
