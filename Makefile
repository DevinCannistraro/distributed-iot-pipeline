# Proto generation runs inside a Docker container (no local protoc needed).
PROTO_IMAGE = proto-gen-builder
PROTO_SRC = proto/freezer/v1/freezer.proto
INGESTION_GEN = ingestion/src/generated
SIMULATOR_GEN = edge-simulator/src/generated

.PHONY: proto-gen test run-ingestion run-edge-simulator docker-up docker-down pull-messages clean

# --- Proto generation ---

proto-gen:
	@echo "==> Building proto-gen image..."
	@docker build -t $(PROTO_IMAGE) -f proto/Dockerfile.protogen proto/
	@echo "==> Generating Python gRPC stubs..."
	@docker run --rm \
		-v $(CURDIR)/proto:/proto \
		-v $(CURDIR)/$(INGESTION_GEN):/out/ingestion \
		-v $(CURDIR)/$(SIMULATOR_GEN):/out/simulator \
		$(PROTO_IMAGE) sh -c ' \
			mkdir -p /tmp/gen && \
			python -m grpc_tools.protoc \
				-I/proto \
				--python_out=/tmp/gen \
				--grpc_python_out=/tmp/gen \
				/proto/freezer/v1/freezer.proto && \
			cp /tmp/gen/freezer/v1/freezer_pb2.py /out/ingestion/ && \
			cp /tmp/gen/freezer/v1/freezer_pb2_grpc.py /out/ingestion/ && \
			cp /tmp/gen/freezer/v1/freezer_pb2.py /out/simulator/ && \
			cp /tmp/gen/freezer/v1/freezer_pb2_grpc.py /out/simulator/ && \
			sed -i "s/from freezer\.v1 import freezer_pb2 as/import freezer_pb2 as/" \
				/out/ingestion/freezer_pb2_grpc.py \
				/out/simulator/freezer_pb2_grpc.py && \
			echo "Generated stubs in ingestion and edge-simulator" \
		'

# --- Tests (run inside Docker) ---

test: proto-gen
	@echo "==> Running ingestion tests..."
	@docker build -t ingestion-test -f ingestion/Dockerfile.test ingestion/
	@docker run --rm ingestion-test

# --- Local run (Docker Compose) ---

docker-up: proto-gen
	docker compose up --build -d

docker-down:
	docker compose down

run-ingestion: proto-gen
	docker compose up --build -d ingestion

run-edge-simulator: proto-gen
	docker compose up --build edge-simulator

# --- Pub/Sub emulator: pull messages for verification ---

pull-messages:
	@docker compose exec pubsub-emulator \
		bash /scripts/pull_messages.sh

clean:
	rm -f $(INGESTION_GEN)/freezer_pb2*.py $(INGESTION_GEN)/freezer_pb2*.pyi
	rm -f $(SIMULATOR_GEN)/freezer_pb2*.py $(SIMULATOR_GEN)/freezer_pb2*.pyi
	docker compose down -v --remove-orphans 2>/dev/null || true
