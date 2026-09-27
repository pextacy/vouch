"""The tool/technology vocabulary the verifier treats as un-inventable.

A term in here can only appear in generated text if the source CV lines contain
it (or one of its synonyms). That is stricter than the proper-noun rule, which
is why lowercase-written tools (`kubernetes`, `postgres`) need to be listed —
capitalisation alone would not catch them.

Recall matters more than size: a term that is missing here still has to clear
the proper-noun rule if it is capitalised, so the gap only opens for a
lowercase-written tool nobody listed. Add to :data:`CANONICAL` when a user
reports a leak, and add a test for it in the same commit.
"""

from __future__ import annotations

from typing import Final

from ..text import normalize_token

#: canonical term → alternative spellings that mean the same thing.
CANONICAL: Final[dict[str, tuple[str, ...]]] = {
    # — languages —
    "python": ("py", "python3"),
    "javascript": ("js", "ecmascript"),
    "typescript": ("ts",),
    "java": (),
    "kotlin": (),
    "swift": (),
    "objective-c": ("objc",),
    "c": (),
    "c++": ("cpp", "cplusplus"),
    "c#": ("csharp",),
    "go": ("golang",),
    "rust": (),
    "ruby": (),
    "php": (),
    "scala": (),
    "perl": (),
    "r": (),
    "matlab": (),
    "julia": (),
    "elixir": (),
    "erlang": (),
    "haskell": (),
    "clojure": (),
    "dart": (),
    "lua": (),
    "bash": ("shell", "sh", "zsh"),
    "powershell": (),
    "sql": (),
    "plsql": ("pl/sql",),
    "tsql": ("t-sql",),
    "solidity": (),
    "assembly": (),
    "vba": (),
    "cobol": (),
    "abap": (),
    # — frontend —
    "react": ("reactjs", "react.js"),
    "next.js": ("nextjs", "next"),
    "vue": ("vuejs", "vue.js"),
    "nuxt": ("nuxtjs",),
    "angular": ("angularjs",),
    "svelte": ("sveltekit",),
    "preact": (),
    "solidjs": (),
    "ember": ("emberjs",),
    "jquery": (),
    "redux": (),
    "mobx": (),
    "zustand": (),
    "tanstack query": ("react query", "reactquery"),
    "webpack": (),
    "vite": (),
    "rollup": (),
    "esbuild": (),
    "babel": (),
    "parcel": (),
    "tailwind": ("tailwindcss",),
    "bootstrap": (),
    "material ui": ("mui",),
    "chakra ui": (),
    "sass": ("scss",),
    "less": (),
    "styled-components": (),
    "storybook": (),
    "three.js": ("threejs",),
    "d3": ("d3.js",),
    "webgl": (),
    "webassembly": ("wasm",),
    "html": ("html5",),
    "css": ("css3",),
    "electron": (),
    "react native": ("reactnative",),
    "flutter": (),
    "ionic": (),
    "expo": (),
    "swiftui": (),
    "jetpack compose": (),
    # — backend / frameworks —
    "node.js": ("node", "nodejs"),
    "deno": (),
    "bun": (),
    "express": ("expressjs",),
    "nestjs": ("nest",),
    "fastify": (),
    "django": (),
    "flask": (),
    "fastapi": (),
    "tornado": (),
    "celery": (),
    "sqlalchemy": (),
    "pydantic": (),
    "spring": ("spring boot", "springboot"),
    "hibernate": (),
    "micronaut": (),
    "quarkus": (),
    "rails": ("ruby on rails", "ror"),
    "sinatra": (),
    "laravel": (),
    "symfony": (),
    "asp.net": ("aspnet", "asp.net core"),
    ".net": ("dotnet", ".net core"),
    "entity framework": ("ef core",),
    "gin": (),
    "fiber": (),
    "echo": (),
    "actix": (),
    "axum": (),
    "phoenix": (),
    "graphql": (),
    "apollo": (),
    "grpc": (),
    "rest": ("restful",),
    "openapi": ("swagger",),
    "soap": (),
    "websocket": ("websockets",),
    "trpc": (),
    # — data stores —
    "postgresql": ("postgres", "psql"),
    "mysql": (),
    "mariadb": (),
    "sqlite": (),
    "oracle": ("oracle db",),
    "sql server": ("mssql", "microsoft sql server"),
    "mongodb": ("mongo",),
    "cassandra": (),
    "dynamodb": (),
    "redis": (),
    "memcached": (),
    "elasticsearch": ("elastic", "opensearch"),
    "solr": (),
    "neo4j": (),
    "influxdb": (),
    "clickhouse": (),
    "snowflake": (),
    "bigquery": (),
    "redshift": (),
    "databricks": (),
    "duckdb": (),
    "cockroachdb": (),
    "couchbase": (),
    "firestore": (),
    "supabase": (),
    "pinecone": (),
    "weaviate": (),
    "qdrant": (),
    "milvus": (),
    "pgvector": (),
    # — infra / platform —
    "kubernetes": ("k8s",),
    "docker": (),
    "podman": (),
    "containerd": (),
    "helm": (),
    "terraform": (),
    "pulumi": (),
    "ansible": (),
    "chef": (),
    "puppet": (),
    "vagrant": (),
    "packer": (),
    "openshift": (),
    "nomad": (),
    "consul": (),
    "vault": (),
    "istio": (),
    "linkerd": (),
    "envoy": (),
    "nginx": (),
    "apache": ("httpd",),
    "haproxy": (),
    "traefik": (),
    "caddy": (),
    "aws": ("amazon web services",),
    "azure": ("microsoft azure",),
    "gcp": ("google cloud", "google cloud platform"),
    "digitalocean": (),
    "heroku": (),
    "vercel": (),
    "netlify": (),
    "cloudflare": (),
    "fly.io": ("flyio",),
    "railway": (),
    "render": (),
    "lambda": ("aws lambda",),
    "ec2": (),
    "s3": (),
    "rds": (),
    "eks": (),
    "ecs": (),
    "fargate": (),
    "cloudfront": (),
    "route53": (),
    "cloudformation": (),
    "sqs": (),
    "sns": (),
    "eventbridge": (),
    "step functions": (),
    "app engine": (),
    "cloud run": (),
    "cloud functions": (),
    "aks": (),
    "azure functions": (),
    # — data / ml —
    "pandas": (),
    "numpy": (),
    "scipy": (),
    "scikit-learn": ("sklearn",),
    "tensorflow": ("tf",),
    "pytorch": ("torch",),
    "keras": (),
    "jax": (),
    "xgboost": (),
    "lightgbm": (),
    "catboost": (),
    "hugging face": ("huggingface", "transformers"),
    "langchain": (),
    "llamaindex": (),
    "openai": (),
    "anthropic": (),
    "spark": ("pyspark", "apache spark"),
    "hadoop": (),
    "hive": (),
    "flink": (),
    "beam": ("apache beam",),
    "kafka": ("apache kafka",),
    "rabbitmq": (),
    "pulsar": (),
    "nats": (),
    "airflow": ("apache airflow",),
    "dagster": (),
    "prefect": (),
    "dbt": (),
    "fivetran": (),
    "looker": (),
    "tableau": (),
    "power bi": ("powerbi",),
    "metabase": (),
    "superset": (),
    "matplotlib": (),
    "seaborn": (),
    "plotly": (),
    "jupyter": ("jupyter notebook",),
    "mlflow": (),
    "kubeflow": (),
    "sagemaker": (),
    "vertex ai": (),
    # — devops / tooling —
    "git": (),
    "github": (),
    "gitlab": (),
    "bitbucket": (),
    "github actions": (),
    "gitlab ci": ("gitlab-ci",),
    "jenkins": (),
    "circleci": (),
    "travis ci": ("travisci",),
    "teamcity": (),
    "bamboo": (),
    "argocd": ("argo cd",),
    "flux": ("fluxcd",),
    "spinnaker": (),
    "sonarqube": (),
    "prometheus": (),
    "grafana": (),
    "datadog": (),
    "new relic": ("newrelic",),
    "sentry": (),
    "splunk": (),
    "elk": ("elk stack",),
    "kibana": (),
    "logstash": (),
    "opentelemetry": ("otel",),
    "jaeger": (),
    "pagerduty": (),
    "nagios": (),
    "zabbix": (),
    # — testing —
    "jest": (),
    "vitest": (),
    "mocha": (),
    "chai": (),
    "jasmine": (),
    "cypress": (),
    "playwright": (),
    "selenium": (),
    "puppeteer": (),
    "testing library": ("react testing library", "rtl"),
    "pytest": (),
    "unittest": (),
    "junit": (),
    "testng": (),
    "rspec": (),
    "phpunit": (),
    "cucumber": (),
    "postman": (),
    "jmeter": (),
    "k6": (),
    "locust": (),
    "gatling": (),
    # — security —
    "oauth": ("oauth2", "oauth 2.0"),
    "openid connect": ("oidc",),
    "saml": (),
    "jwt": (),
    "ldap": (),
    "kerberos": (),
    "tls": ("ssl",),
    "owasp": (),
    "penetration testing": ("pentest", "pen testing"),
    "burp suite": ("burp",),
    "metasploit": (),
    "nmap": (),
    "wireshark": (),
    "soc 2": ("soc2",),
    "iso 27001": ("iso27001",),
    "gdpr": (),
    "kvkk": (),
    "hipaa": (),
    "pci dss": ("pci-dss",),
    # — business / product / design —
    "salesforce": (),
    "hubspot": (),
    "sap": (),
    "netsuite": (),
    "workday": (),
    "servicenow": (),
    "zendesk": (),
    "intercom": (),
    "jira": (),
    "confluence": (),
    "asana": (),
    "trello": (),
    "monday.com": ("monday",),
    "notion": (),
    "linear": (),
    "slack": (),
    "figma": (),
    "sketch": (),
    "adobe xd": (),
    "photoshop": (),
    "illustrator": (),
    "indesign": (),
    "after effects": (),
    "premiere pro": (),
    "blender": (),
    "autocad": (),
    "solidworks": (),
    "revit": (),
    "canva": (),
    "miro": (),
    "amplitude": (),
    "mixpanel": (),
    "google analytics": ("ga4",),
    "segment": (),
    "optimizely": (),
    "braze": (),
    "marketo": (),
    "mailchimp": (),
    "stripe": (),
    "paypal": (),
    "adyen": (),
    "plaid": (),
    "twilio": (),
    "shopify": (),
    "magento": (),
    "woocommerce": (),
    "wordpress": (),
    "contentful": (),
    "strapi": (),
    "sanity": (),
    "excel": ("microsoft excel",),
    "google sheets": (),
    "quickbooks": (),
    "xero": (),
    # — practices & certifications —
    "scrum": (),
    "kanban": (),
    "safe": (),
    "itil": (),
    "six sigma": (),
    "lean": (),
    "prince2": (),
    "pmp": (),
    "cissp": (),
    "ccna": (),
    "comptia": (),
    "aws certified": (),
    "azure certified": (),
    "cfa": (),
    "cpa": (),
    "acca": (),
    "ielts": (),
    "toefl": (),
}


#: Spellings that are also ordinary words ("go to market", "rest of the team",
#: "lean process", "less time"). Matching these as tools on their own would
#: manufacture violations out of plain English, so a one-word match is ignored.
#: The capitalised uses that genuinely name a tool — "Go", "R", "Spring" — are
#: still caught by the proper-noun rule, and multi-word grams such as
#: "spring boot" are always honoured.
AMBIGUOUS_SPELLINGS: Final[frozenset[str]] = frozenset(
    {
        "go", "r", "c", "rest", "restful", "spring", "lean", "safe", "echo",
        "gin", "fiber", "flux", "segment", "render", "linear", "less", "swift",
        "dart", "beam", "hive", "solid", "sh", "py", "ts", "js", "tf", "torch",
        "lambda", "apache", "vault", "consul", "nomad", "notion", "canva",
    }
)


class TechLexicon:
    """Maps any spelling of a term to its canonical form.

    ``matches(text)`` returns the canonical terms present in ``text``; the
    verifier calls it on both the generated sentence and the source lines and
    compares the two sets.
    """

    def __init__(self, entries: dict[str, tuple[str, ...]] | None = None) -> None:
        source = entries if entries is not None else CANONICAL
        self._by_key: dict[str, str] = {}
        self._ambiguous_keys: set[str] = set()
        self._max_words = 1
        for canonical, synonyms in source.items():
            for spelling in (canonical, *synonyms):
                key = normalize_token(spelling)
                if key:
                    self._by_key[key] = canonical
                    if spelling.casefold() in AMBIGUOUS_SPELLINGS:
                        self._ambiguous_keys.add(key)
                words = len(spelling.split())
                self._max_words = max(self._max_words, words)

    def __len__(self) -> int:
        return len(self._by_key)

    def canonical(self, token: str) -> str | None:
        """Return the canonical term for a single token, if it is known."""
        key = normalize_token(token)
        if key in self._ambiguous_keys:
            return None
        return self._by_key.get(key)

    def knows(self, token: str) -> bool:
        """Whether ``token`` names a technology unambiguously."""
        return self.canonical(token) is not None

    def is_ambiguous(self, token: str) -> bool:
        """Whether ``token`` spells a technology that is also an ordinary word.

        "Go" and "R" are tools and English words at once, so the tech rule
        skips them. The proper-noun rule still has to see them on their own —
        glued to the word before them they become a phrase ("Shipped Go") that
        no CV ever contains.
        """
        return normalize_token(token) in self._ambiguous_keys

    def surfaces(self, text: str) -> dict[str, str]:
        """Every canonical term in ``text``, mapped to how ``text`` spells it.

        :meth:`matches` answers "is this term here"; this answers "what did
        they call it". The CV audit needs the second, because a finding is
        shown to the person whose CV it is — telling someone their skills list
        names "grpc" when they wrote "gRPC", or "kubernetes" when they wrote
        "k8s", reads as the app not having looked properly.

        Call it on **raw** text: the point is the capitalisation and spelling
        that normalisation throws away.
        """
        words = text.split()
        found: dict[str, str] = {}
        for size in range(min(self._max_words, len(words)), 0, -1):
            for index in range(len(words) - size + 1):
                gram = " ".join(words[index : index + size])
                key = normalize_token(gram)
                if size == 1 and key in self._ambiguous_keys:
                    continue
                canonical = self._by_key.get(key)
                if canonical and canonical not in found:
                    found[canonical] = gram.strip(" \t,;:./|()[]")
        return found

    def matches(self, text: str) -> set[str]:
        """Every canonical term appearing in ``text``.

        Scans n-grams longest-first so ``google cloud`` wins over ``google``.
        One-word grams listed in :data:`AMBIGUOUS_SPELLINGS` are skipped.
        """
        words = text.split()
        found: set[str] = set()
        for size in range(min(self._max_words, len(words)), 0, -1):
            for index in range(len(words) - size + 1):
                gram = " ".join(words[index : index + size])
                key = normalize_token(gram)
                if size == 1 and key in self._ambiguous_keys:
                    continue
                canonical = self._by_key.get(key)
                if canonical:
                    found.add(canonical)
        return found

    def cover(self, words: list[str]) -> set[int]:
        """Indices of ``words`` consumed by a lexicon match, longest first.

        The verifier uses this to subtract technology names from a capitalised
        phrase before treating the remainder as a proper noun — "Google Cloud"
        is a tool (checked with its synonyms), "Acme Payments" is an employer
        (checked literally), and "Acme Kubernetes Corp" is both.
        """
        taken: set[int] = set()
        for size in range(min(self._max_words, len(words)), 0, -1):
            for index in range(len(words) - size + 1):
                window = range(index, index + size)
                if any(position in taken for position in window):
                    continue
                gram = " ".join(words[index : index + size])
                key = normalize_token(gram)
                if size == 1 and key in self._ambiguous_keys:
                    continue
                if key in self._by_key:
                    taken.update(window)
        return taken


DEFAULT_LEXICON: Final[TechLexicon] = TechLexicon()
