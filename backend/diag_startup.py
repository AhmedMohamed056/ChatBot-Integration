import os, sys, time, shutil, traceback, threading, faulthandler
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parent
DB_DIR = str(BACKEND_DIR / "diag_chroma_db")
DUMP_FILE = str(BACKEND_DIR / "diag_dump.txt")

def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)

def watchdog(timeout=30):
    time.sleep(timeout)
    with open(DUMP_FILE, "w", encoding="utf-8") as f:
        f.write(f"!!! WATCHDOG: hung for {timeout}s - dumping all thread stacks !!!\n\n")
        faulthandler.dump_traceback(file=f, all_threads=True)
        f.write("\n\n--- threading.enumerate() ---\n")
        for t in threading.enumerate():
            f.write(f"  {t.name} daemon={t.daemon} alive={t.is_alive()}\n")
    print(f"!!! WATCHDOG fired after {timeout}s - wrote {DUMP_FILE} !!!", flush=True)
    os._exit(2)

threading.Thread(target=watchdog, args=(180,), daemon=True).start()

def main():
    log("START diag")

    log("STEP 1: import chromadb")
    import chromadb
    log(f"  chromadb version = {chromadb.__version__}")

    log("STEP 2: import langchain_community Chroma")
    from langchain_community.vectorstores import Chroma
    log("  ok")

    log("STEP 3: get_embeddings (HuggingFaceEmbeddings)")
    from langchain_huggingface import HuggingFaceEmbeddings
    emb = HuggingFaceEmbeddings(model_name="intfloat/multilingual-e5-base")
    log("  embeddings loaded")

    log("STEP 4: list supported files")
    from document_service import list_supported_files, split_file
    files = list_supported_files()
    log(f"  found {len(files)} file(s)")
    all_docs = []
    for f in files:
        all_docs.extend(split_file(str(f)))
    log(f"  total chunks = {len(all_docs)}")

    if os.path.exists(DB_DIR):
        shutil.rmtree(DB_DIR)

    log("STEP 5: chromadb.config.Settings(is_persistent=True) + persist_directory")
    settings = chromadb.config.Settings(is_persistent=True)
    settings.persist_directory = DB_DIR
    log("  ok")

    log("STEP 6: chromadb.Client(settings)")
    client = chromadb.Client(settings)
    log("  ok")

    log("STEP 7: client.get_or_create_collection(name='langchain', embedding_function=None)")
    collection = client.get_or_create_collection(name="langchain", embedding_function=None)
    log("  ok")

    log("STEP 8: embed_documents (generate embeddings)")
    texts = [d.page_content for d in all_docs]
    metadatas = [d.metadata for d in all_docs]
    embeddings = emb.embed_documents(texts)
    log(f"  embeddings generated: {len(embeddings)} vectors, dim={len(embeddings[0])}")

    import uuid
    ids = [str(uuid.uuid4()) for _ in texts]

    log("STEP 9: collection.upsert(...)  <-- suspected hang location")
    t0 = time.time()
    try:
        collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
        log(f"  upsert returned in {time.time()-t0:.2f}s")
    except Exception as e:
        log(f"  upsert EXCEPTION: {e}")
        traceback.print_exc()
        return

    log("STEP 10: collection.count()")
    log(f"  count = {collection.count()}")

    log("STEP 11: Chroma.from_documents (real startup path)")
    if os.path.exists(DB_DIR):
        shutil.rmtree(DB_DIR)

    class ProgressEmb:
        def embed_documents(self, t):
            log("    ProgressEmb.embed_documents START")
            r = emb.embed_documents(t)
            log(f"    ProgressEmb.embed_documents DONE ({len(r)} vecs)")
            return r
        def embed_query(self, t):
            return emb.embed_query(t)
        def __getattr__(self, n):
            if n == "_base": raise AttributeError(n)
            return getattr(emb, n)

    log("STEP 11a: Chroma.from_documents(...)")
    t0 = time.time()
    try:
        vs = Chroma.from_documents(documents=all_docs, embedding=ProgressEmb(), persist_directory=DB_DIR)
        log(f"  from_documents returned in {time.time()-t0:.2f}s")
    except Exception as e:
        log(f"  from_documents EXCEPTION: {e}")
        traceback.print_exc()
        return

    log("STEP 12: vs.as_retriever")
    retriever = vs.as_retriever(search_kwargs={"k": 3})
    log("  ok")

    log("DONE diag - everything returned successfully")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("EXCEPTION:")
        traceback.print_exc()