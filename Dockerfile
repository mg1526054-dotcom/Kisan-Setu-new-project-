FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Seed the database and train the model at build time so the image is
# immediately ready to serve. For real deployments, replace data/seed.py
# with a real AGMARKNET/e-NAM ingestion job before this step.
RUN python data/seed.py && python ml/train.py

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
