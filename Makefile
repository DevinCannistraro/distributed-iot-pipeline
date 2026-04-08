# Proto generation runs inside a Docker container (no local protoc needed).
PROTO_IMAGE = proto-gen-builder
PROTO_SRC = proto/freezer/v1/freezer.proto
INGESTION_GEN = ingestion/src/generated
SIMULATOR_GEN = edge-simulator/src/generated
PROCESSOR_GEN = processor/src/generated

.PHONY: proto-gen test test-processor docker-up docker-down run-ingestion run-edge-simulator run-simulator-cloud pull-messages clean

# --- Proto generation ---

proto-gen:
	@echo "==> Building proto-gen image..."
	@docker build -t $(PROTO_IMAGE) -f proto/Dockerfile.protogen proto/
	@echo "==> Generating Python gRPC stubs..."
	@docker run --rm \
		-v $(CURDIR)/proto:/proto \
		-v $(CURDIR)/$(INGESTION_GEN):/out/ingestion \
		-v $(CURDIR)/$(SIMULATOR_GEN):/out/simulator \
		-v $(CURDIR)/$(PROCESSOR_GEN):/out/processor \
		$(PROTO_IMAGE) sh -c ' \
			mkdir -p /tmp/gen && \
			python -m grpc_tools.protoc \
				-I/proto \
				--python_out=/tmp/gen \
				--grpc_python_out=/tmp/gen \
				/proto/freezer/v1/freezer.proto && \
			for dest in ingestion simulator processor; do \
				cp /tmp/gen/freezer/v1/freezer_pb2.py /out/$$dest/ && \
				cp /tmp/gen/freezer/v1/freezer_pb2_grpc.py /out/$$dest/ ; \
			done && \
			sed -i "s/from freezer\.v1 import freezer_pb2 as/import freezer_pb2 as/" \
				/out/ingestion/freezer_pb2_grpc.py \
				/out/simulator/freezer_pb2_grpc.py \
				/out/processor/freezer_pb2_grpc.py && \
			echo "Generated stubs in ingestion, edge-simulator, and processor" \
		'

# --- Tests (run inside Docker) ---

test: proto-gen
	@echo "==> Running ingestion tests..."
	@docker build -t ingestion-test -f ingestion/Dockerfile.test ingestion/
	@docker run --rm ingestion-test

test-processor: proto-gen
	@echo "==> Starting Firestore emulator for tests..."
	@docker compose up -d firestore-emulator
	@echo "==> Waiting for Firestore emulator to be healthy..."
	@until docker compose exec -T firestore-emulator curl -sf http://localhost:8080/ > /dev/null 2>&1; do sleep 1; done
	@echo "==> Running processor tests..."
	@docker build -t processor-test -f processor/Dockerfile.test processor/
	@docker run --rm \
		--network $$(docker compose ps -q firestore-emulator | xargs docker inspect --format='{{range .NetworkSettings.Networks}}{{.NetworkID}}{{end}}' | head -1) \
		-e FIRESTORE_EMULATOR_HOST=firestore-emulator:8080 \
		-e GCP_PROJECT_ID=local-dev \
		processor-test
	@echo "==> Stopping Firestore emulator..."
	@docker compose stop firestore-emulator

test-all: test test-processor

# --- Local run (Docker Compose) ---

docker-up: proto-gen
	docker compose up --build -d

docker-down:
	docker compose down

run-ingestion: proto-gen
	docker compose up --build -d ingestion

run-edge-simulator: proto-gen
	docker compose up --build edge-simulator

# Run edge simulator against the deployed Cloud Run ingestion service (requires pi-sa-key.json)
run-simulator-cloud: proto-gen
	docker build -t edge-sim-cloud ./edge-simulator
	docker run --rm \
		-v $(CURDIR)/edge-simulator/pi-sa-key.json:/app/pi-sa-key.json:ro \
		edge-sim-cloud \
		python src/run.py \
			--target ingestion-884148543484.us-east1.run.app:443 \
			--sa-key /app/pi-sa-key.json \
			--interval 30

# --- Pub/Sub emulator: pull messages for verification ---

pull-messages:
	@docker compose exec pubsub-emulator \
		bash /scripts/pull_messages.sh

clean:
	rm -f $(INGESTION_GEN)/freezer_pb2*.py $(INGESTION_GEN)/freezer_pb2*.pyi
	rm -f $(SIMULATOR_GEN)/freezer_pb2*.py $(SIMULATOR_GEN)/freezer_pb2*.pyi
	rm -f $(PROCESSOR_GEN)/freezer_pb2*.py $(PROCESSOR_GEN)/freezer_pb2*.pyi
	docker compose down -v --remove-orphans 2>/dev/null || true
