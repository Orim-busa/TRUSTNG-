"""Shared ISO 3166-1 alpha-2 country-code validation."""

import pycountry


ERROR_MESSAGE = (
    "Corridor countries must use valid ISO 3166-1 alpha-2 country codes."
)


def normalize_country_code(value):
    if not isinstance(value, str):
        raise ValueError(ERROR_MESSAGE)

    normalized = value.strip().upper()

    if len(normalized) != 2:
        raise ValueError(ERROR_MESSAGE)

    if pycountry.countries.get(alpha_2=normalized) is None:
        raise ValueError(ERROR_MESSAGE)

    return normalized


def normalize_corridor_countries(sender_country, receiver_country):
    if (sender_country is None) != (receiver_country is None):
        raise ValueError(
            "Sender and receiver countries must be supplied together."
        )

    if sender_country is None:
        return None, None

    return (
        normalize_country_code(sender_country),
        normalize_country_code(receiver_country),
    )
