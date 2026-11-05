"""集中角色常數；新檔案優先採用，既有檔案各自的 tuple 不強制改寫。"""

CAREGIVER = "caregiver"
SUPERVISOR = "supervisor"
DIRECTOR = "director"
ADMIN = "admin"

ALL_STAFF = (CAREGIVER, SUPERVISOR, DIRECTOR, ADMIN)
REVIEWERS = (SUPERVISOR, DIRECTOR, ADMIN)
APPROVERS = (DIRECTOR, ADMIN)
