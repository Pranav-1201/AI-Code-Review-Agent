from app.services.retriever_service import CodeRetriever

retriever = CodeRetriever()

query = "nested loops inefficiency"

results = retriever.retrieve(query)

for r in results:
    print(r)