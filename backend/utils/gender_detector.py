"""
Gender detection from first names.

Uses curated lists of Filipino/Spanish/English names to determine
how ARIA should formally address candidates (Mr./Ms. + last name).
"""

# Common Filipino/Spanish/English male first names
MALE_NAMES = {
    # Filipino male names
    'juan', 'jose', 'mario', 'carlo', 'carlos',
    'miguel', 'antonio', 'manuel', 'roberto',
    'eduardo', 'fernando', 'francisco', 'pedro',
    'angelo', 'mark', 'john', 'james', 'joseph',
    'michael', 'ryan', 'christian', 'daniel',
    'gabriel', 'rafael', 'david', 'paul', 'peter',
    'luis', 'ricky', 'rico', 'rome',
    'rommel', 'rodel', 'roderick', 'randy',
    'jerome', 'jayson', 'jericho',
    'aldrin', 'alvin', 'arnold', 'arnel',
    'arvin', 'alexis', 'alex', 'allen', 'allan',
    'albert', 'alfred', 'alfredo', 'arthur',
    'ben', 'benjamin', 'bernard', 'bernie',
    'bryan', 'brian', 'bruce', 'carl',
    'christopher', 'clarence',
    'clark', 'clement', 'cliff', 'clifford',
    'cris', 'cristopher', 'darwin', 'dave',
    'dexter', 'dino', 'dominic', 'dondon',
    'edgar', 'edgardo', 'edmond', 'edmund',
    'edson', 'edward', 'erwin', 'felix',
    'ferdinand', 'gene', 'george', 'gerald',
    'gerard', 'gilbert', 'glen', 'glenn',
    'gregorio', 'hector', 'henry', 'herbert',
    'homer', 'ian', 'ivan', 'jomar', 'jonas',
    'jonathan', 'jordy', 'jorge', 'jovito',
    'julius', 'junrey', 'kevin', 'kenneth',
    'kyle', 'lance', 'larry', 'laurence',
    'lawrence', 'leo', 'leon', 'leonard',
    'lester', 'lloyd', 'lorenz', 'lorenzo',
    'louie', 'lowie', 'lyle', 'marc',
    'marko', 'martin', 'marvin', 'matthew',
    'max', 'melvin', 'mike', 'neil', 'nelson',
    'nestor', 'nick', 'nicolas', 'noel', 'norman',
    'oliver', 'omar', 'oscar', 'patrick', 'paulo',
    'philip', 'phillip', 'ralph', 'raul', 'raymond',
    'renato', 'renren', 'rex', 'reynaldo',
    'richard', 'rick', 'robert', 'robin',
    'rodolfo', 'rodrigo', 'rogelio', 'roger',
    'rolando', 'roman', 'romeo', 'ronald',
    'ronaldo', 'ronnie', 'roque', 'ruben',
    'rudy', 'samuel', 'santiago', 'sergio',
    'stephen', 'steven', 'teodoro', 'thomas',
    'timothy', 'tirso', 'tomas', 'tony',
    'victor', 'vincent', 'virgilio', 'walter',
    'wilfredo', 'william', 'wilson', 'xavier',
}

# Common Filipino/Spanish/English female first names
FEMALE_NAMES = {
    # Filipino female names
    'maria', 'mary', 'ana', 'anna', 'anne',
    'angela', 'angel', 'angelica', 'andrea',
    'abigail', 'abby', 'alyssa', 'amanda',
    'amor', 'amy', 'april', 'arlyn', 'armie',
    'baby', 'bea', 'beatrice', 'bella', 'beth',
    'camille', 'carla', 'carly', 'carmen',
    'carol', 'caroline', 'catherine', 'cecile',
    'cecilia', 'charlene', 'charlotte', 'cherry',
    'cherie', 'christina', 'christine', 'cindy',
    'clara', 'clarissa', 'claudia', 'crystal',
    'daisy', 'dana', 'daniela', 'danielle',
    'dawn', 'deborah', 'diana', 'dianne',
    'donna', 'dora', 'doris', 'dorothy',
    'elena', 'elisa', 'elizabeth', 'ella',
    'ellen', 'elsa', 'emily', 'emma', 'erica',
    'erika', 'esther', 'eva', 'evelyn',
    'faith', 'fatima', 'fiona', 'florence',
    'frances', 'francisca', 'gina', 'gloria',
    'grace', 'hannah', 'hazel', 'helen',
    'iris', 'isabel', 'isabella', 'ivy',
    'jackie', 'jasmine', 'jean', 'jeanette',
    'jemimah', 'jennifer', 'jenny', 'jessica',
    'joanna', 'joy', 'joyce', 'judith', 'judy',
    'julia', 'julie', 'juliet', 'karen',
    'kate', 'katherine', 'kathleen', 'kathryn',
    'katrina', 'kim', 'kimberly', 'kristine',
    'laura', 'lauren', 'lea', 'leah', 'lena',
    'leslie', 'linda', 'lisa', 'liza', 'lorena',
    'lorraine', 'lourdes', 'lucia', 'lucy',
    'luisa', 'luna', 'lydia', 'lynn', 'mae',
    'margaret', 'margarita', 'marie', 'marina',
    'marissa', 'martha', 'melanie', 'melissa',
    'mercedes', 'michelle', 'mila', 'mildred',
    'miriam', 'monique', 'nancy', 'natalie',
    'nicole', 'nina', 'nora', 'norma', 'olivia',
    'pamela', 'patricia', 'paula', 'pauline',
    'rachelle', 'rachel', 'rebecca', 'regina',
    'rhea', 'rhoda', 'rita', 'rosa', 'rosalie',
    'rosanna', 'rosario', 'rose', 'roselyn',
    'rowena', 'ruby', 'ruth', 'sabrina', 'sarah',
    'sharon', 'sheila', 'shirley', 'silvia',
    'sofia', 'sonia', 'sophia', 'stephanie',
    'susan', 'suzanne', 'tanya', 'teresa',
    'tina', 'tricia', 'vanessa', 'vera',
    'victoria', 'virginia', 'vivian', 'wendy',
    'yvonne', 'zara', 'zoe',
}


def detect_gender_from_name(full_name: str) -> dict:
    """
    Detect gender from full name.

    Args:
        full_name: The candidate's full name.

    Returns:
        Dict with gender, title, confidence, first_name, and full_name.

    Examples:
        >>> detect_gender_from_name("Juan Dela Cruz")
        {'gender': 'male', 'title': 'Mr.', 'confidence': 'high', ...}
        >>> detect_gender_from_name("Maria Santos")
        {'gender': 'female', 'title': 'Ms.', 'confidence': 'high', ...}
    """
    if not full_name:
        return {
            "gender": "unknown",
            "title": "",
            "confidence": "low",
            "first_name": "",
            "full_name": "",
        }

    # Get first name only
    parts = full_name.strip().split()
    first_name = parts[0].lower() if parts else ""

    # Remove common prefixes if already in name
    if first_name in ('mr', 'mrs', 'ms', 'dr', 'prof'):
        first_name = parts[1].lower() if len(parts) > 1 else ""
        parts = parts[1:]  # Shift parts for proper name extraction

    if first_name in MALE_NAMES:
        return {
            "gender": "male",
            "title": "Mr.",
            "confidence": "high",
            "first_name": parts[0].title() if parts else "",
            "full_name": full_name.strip().title(),
        }

    if first_name in FEMALE_NAMES:
        return {
            "gender": "female",
            "title": "Ms.",
            "confidence": "high",
            "first_name": parts[0].title() if parts else "",
            "full_name": full_name.strip().title(),
        }

    # Unknown — use first name only, no title
    return {
        "gender": "unknown",
        "title": "",
        "confidence": "low",
        "first_name": parts[0].title() if parts else full_name.strip().title(),
        "full_name": full_name.strip().title(),
    }


def get_candidate_address(full_name: str) -> str:
    """
    Get how ARIA should address the candidate.

    If gender is known with high confidence, returns "Mr./Ms. LastName".
    Otherwise, returns just the first name.

    Args:
        full_name: The candidate's full name.

    Returns:
        Formal address string for ARIA to use.

    Examples:
        >>> get_candidate_address("Juan Dela Cruz")
        'Mr. Dela Cruz'
        >>> get_candidate_address("Maria Santos")
        'Ms. Santos'
        >>> get_candidate_address("Kyle Austria")
        'Mr. Austria'
        >>> get_candidate_address("Xander Unknown")
        'Xander'
    """
    result = detect_gender_from_name(full_name)

    if result["confidence"] == "high":
        # Use formal title + last name
        parts = full_name.strip().split()
        # Skip title prefixes if present
        if parts and parts[0].lower() in ('mr', 'mrs', 'ms', 'dr', 'prof'):
            parts = parts[1:]
        last_name = parts[-1].title() if parts else full_name.strip().title()
        return f"{result['title']} {last_name}"
    else:
        # Unknown gender — use first name only
        return result["first_name"]
