# English Test Cases Example - Agentic QA Maestro

This file demonstrates how to write test cases in plain English for the English Test Pipeline.

## Test Case 1

ID: TC001
Title: User Login with Valid Credentials
Description: Verify that a user can login successfully with valid credentials
Priority: High

Steps:
1. Navigate to the application login page
2. Enter valid username in the username field
3. Enter valid password in the password field
4. Click the Login button
5. Wait for the dashboard to load
6. Verify that the user is redirected to the dashboard

Expected Result: User should be logged in successfully and see the main dashboard

---

## Test Case 2

ID: TC002
Title: User Logout
Description: Verify that a user can logout successfully
Priority: High

Steps:
1. Login with valid credentials (already logged in)
2. Click on the user profile menu in the top right corner
3. Click the "Logout" button
4. Verify that the user is redirected back to the login page

Expected Result: User should be logged out and redirected to the login page

---

## Test Case 3

ID: TC003
Title: Verify Error Message for Invalid Password
Description: Verify that an error message appears when logging in with invalid password
Priority: Medium

Steps:
1. Navigate to the application login page
2. Enter valid username
3. Enter invalid password
4. Click the Login button
5. Verify that an error message appears

Expected Result: An error message should appear saying "Invalid password" or similar

---

## Test Case 4

ID: TC004
Title: View User Profile
Description: Verify that user can view their profile information
Priority: Medium

Steps:
1. Login with valid credentials
2. Click on the user profile icon
3. Click "View Profile"
4. Verify that all user information is displayed correctly
5. Click "Close" or navigate back

Expected Result: User profile information should be displayed correctly

---

## Test Case 5

ID: TC005
Title: Change Application Settings
Description: Verify that user can change application settings
Priority: Low

Steps:
1. Login with valid credentials
2. Navigate to Settings
3. Click on "Preferences"
4. Change the theme from "Light" to "Dark"
5. Click "Save"
6. Verify that the theme has changed to dark

Expected Result: Application theme should change to dark mode and the setting should be saved
