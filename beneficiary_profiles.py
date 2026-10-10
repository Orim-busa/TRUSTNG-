BENEFICIARY_PROFILES = {

    "user_002": {
        "verification_level": "VERIFIED",
        "successful_transactions": 120,
        "disputes": 1,
        "suspicious_events": 0,
        "account_age_days": 540,

        # Security history
        "failed_transactions": 2,
        "account_changes": 1,
        "device_changes": 1,
        "chargebacks": 0,

        # Behaviour
        "average_transaction_amount": 75000,
        "usual_channels": ["BANK", "MOBILE"],
        "usual_countries": ["NG"],

        # Relationship history
        "known_senders": 18,
        "successful_sender_relationships": 15
    },

    "user_003": {
        "verification_level": "BASIC",
        "successful_transactions": 3,
        "disputes": 0,
        "suspicious_events": 1,
        "account_age_days": 12,

        # Security history
        "failed_transactions": 4,
        "account_changes": 3,
        "device_changes": 2,
        "chargebacks": 1,

        # Behaviour
        "average_transaction_amount": 15000,
        "usual_channels": ["MOBILE"],
        "usual_countries": ["NG"],

        # Relationship history
        "known_senders": 2,
        "successful_sender_relationships": 1
    }

}


def get_beneficiary_profile(beneficiary_id):

    return BENEFICIARY_PROFILES.get(
        beneficiary_id,
        {
            "verification_level": "UNKNOWN",
            "successful_transactions": 0,
            "disputes": 0,
            "suspicious_events": 0,
            "account_age_days": 0,

            "failed_transactions": 0,
            "account_changes": 0,
            "device_changes": 0,
            "chargebacks": 0,

            "average_transaction_amount": 0,
            "usual_channels": [],
            "usual_countries": [],

            "known_senders": 0,
            "successful_sender_relationships": 0
        }
    )