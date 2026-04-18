from models.schemas import AuditResponse, Claim, Evidence

# Pre-built sample audit response used by GET /sample
SAMPLE_RESPONSE = AuditResponse(
    document=(
        "The Earth orbits the Sun at an average distance of 93 million miles. "
        "Python is the best programming language and always outperforms every other language. "
        "Machine learning models can improve over time with more data. "
        "The human brain contains approximately 86 billion neurons. "
        "Renewable energy is always cheaper than fossil fuels in every region."
    ),
    claims=[
        Claim(
            text="The Earth orbits the Sun at an average distance of 93 million miles.",
            status="Verified",
            confidence=0.92,
            start_idx=0,
            end_idx=68,
            evidence=[
                Evidence(
                    title="NASA Solar System Exploration",
                    snippet="Earth orbits the Sun at a mean distance of about 93 million miles (150 million km).",
                    url="https://solarsystem.nasa.gov/planets/earth/overview/",
                    support="supporting",
                ),
                Evidence(
                    title="Encyclopedia Britannica – Earth",
                    snippet="The mean distance from Earth to the Sun is approximately 149.6 million km.",
                    url="https://www.britannica.com/place/Earth",
                    support="supporting",
                ),
            ],
        ),
        Claim(
            text="Python is the best programming language and always outperforms every other language.",
            status="Hallucination",
            confidence=0.81,
            start_idx=69,
            end_idx=153,
            evidence=[
                Evidence(
                    title="Stack Overflow Developer Survey 2023",
                    snippet="Python is highly popular, but performance benchmarks show it trailing compiled languages.",
                    url="https://survey.stackoverflow.co/2023/",
                    support="weak",
                ),
            ],
        ),
        Claim(
            text="Machine learning models can improve over time with more data.",
            status="Plausible",
            confidence=0.74,
            start_idx=154,
            end_idx=215,
            evidence=[
                Evidence(
                    title="Google AI Blog – Scaling Laws",
                    snippet="Larger datasets generally lead to improved model performance across most architectures.",
                    url="https://ai.googleblog.com/scaling-laws",
                    support="supporting",
                ),
            ],
        ),
        Claim(
            text="The human brain contains approximately 86 billion neurons.",
            status="Verified",
            confidence=0.89,
            start_idx=216,
            end_idx=274,
            evidence=[
                Evidence(
                    title="Azevedo et al., 2009 – Journal of Comparative Neurology",
                    snippet="Revised estimates place the total neuron count at roughly 86 billion.",
                    url="https://doi.org/10.1002/cne.21974",
                    support="supporting",
                ),
            ],
        ),
        Claim(
            text="Renewable energy is always cheaper than fossil fuels in every region.",
            status="Hallucination",
            confidence=0.77,
            start_idx=275,
            end_idx=344,
            evidence=[
                Evidence(
                    title="IEA Renewables Report 2023",
                    snippet="Levelised costs vary significantly by region; fossil fuels remain cheaper in some markets.",
                    url="https://www.iea.org/reports/renewables-2023",
                    support="weak",
                ),
            ],
        ),
    ],
    total=5,
    verified=2,
    plausible=1,
    hallucinations=2,
)
