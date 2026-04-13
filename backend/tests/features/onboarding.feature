Feature: First-Run Onboarding
  As a new DevLog+ user
  I want to complete an initial profiling flow
  So the system has baseline context for generating content

  Scenario: Onboarding not completed initially
    When I check the onboarding status
    Then onboarding should not be completed

  Scenario: Complete the onboarding flow
    When I complete onboarding with the following details:
      | primary_languages | Python, Go          |
      | years_experience  | 5                   |
      | primary_domain    | backend             |
      | go_level          | beginner            |
      | topic_interests   | concurrency, testing|
    Then onboarding should be completed
    And the onboarding state should have go experience level "beginner"
