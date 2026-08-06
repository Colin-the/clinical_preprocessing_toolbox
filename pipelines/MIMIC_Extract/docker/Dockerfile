# MIMIC-Extract Docker image
# includes PostgreSQL client, mimic-code, Python env, and extraction tools
# matches parameters from build_curated_from_psql.sh
#

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV MIMIC_CODE_VERSION=762943eab64deb30bdb2abcf7db43602ccb25908

# install system dependencies: PostgreSQL client, build tools, gzip, git
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    gzip \
    git \
    curl \
    ca-certificates \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Miniconda
RUN curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/miniconda.sh \
    && bash /tmp/miniconda.sh -b -p /opt/conda \
    && rm /tmp/miniconda.sh
ENV PATH="/opt/conda/bin:$PATH"

# accept conda ToS
RUN conda config --set allow_conda_downgrades true \
    && conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main \
    && conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r \
    && conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/msys2

# create conda environment matching MIMIC-Extract requirements
RUN conda create -n mimic_data_extraction -y python=3.9 \
    numpy pandas scipy jupyter numexpr scikit-learn psycopg2 pytables matplotlib \
    boto3 sqlalchemy spacy nltk tqdm pip \
    && conda run -n mimic_data_extraction pip install datapackage scispacy tables

# download spacy model
RUN conda run -n mimic_data_extraction python -m spacy download en_core_web_sm

# Clone mimic-code 
RUN git clone https://github.com/MIT-LCP/mimic-code.git /opt/mimic-code \
    && cd /opt/mimic-code && git checkout ${MIMIC_CODE_VERSION}

# Patch mimic-code postgres_make_concepts.sh to use CONNSTR from env 
RUN sed -i "s/export CONNSTR='-d mimic'/\[ -z \"\$CONNSTR\" \] \\&\\& export CONNSTR='-d mimic'/" /opt/mimic-code/concepts/postgres_make_concepts.sh

# Copy MIMIC-Extract code 
COPY . /opt/mimic-extract
# Convert entrypoint to Unix line endings 
RUN sed -i 's/\r$//' /opt/mimic-extract/docker/entrypoint.sh
RUN chmod +x /opt/mimic-extract/docker/entrypoint.sh
WORKDIR /opt/mimic-extract

# make output directory
RUN mkdir -p /opt/mimic-extract/data/curated

# Default environment variables 
ENV PGHOST=postgres
ENV PGPORT=5432
ENV PGDATABASE=mimic
ENV PGUSER=mimic
ENV PGPASSWORD=mimic
ENV MIMIC_CODE_DIR=/opt/mimic-code
ENV MIMIC_EXTRACT_CODE_DIR=/opt/mimic-extract
ENV MIMIC_DATA_DIR=/mimic_data
ENV MIMIC_EXTRACT_OUTPUT_DIR=/opt/mimic-extract/data/curated
ENV NUMERICS_BATCH_SIZE=0

ENTRYPOINT ["/opt/mimic-extract/docker/entrypoint.sh"]
