"""
core/rag/embedder.py — ko-sroberta-multitask 로컬 임베딩

모델을 모듈 수준에서 싱글턴으로 캐싱해 반복 로드 방지.
"""

from sentence_transformers import SentenceTransformer

MODEL_NAME = "snunlp/KR-SBERT-V40K-klueNLI-augSTS"
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        print(f"[embedder] 모델 로드 중: {MODEL_NAME}")
        _model = SentenceTransformer(MODEL_NAME)
        print("[embedder] 모델 로드 완료")
    return _model


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """텍스트 리스트 → 벡터 리스트"""
    model = get_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return embeddings.tolist()


def embed_query(text: str) -> list[float]:
    """단일 쿼리 임베딩"""
    model = get_model()
    vec = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
    return vec.tolist()
