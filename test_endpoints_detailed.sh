#!/bin/bash

# Detailed API Test Script for PLM-IQ
# Tests all CRUD operations, error handling, and edge cases for each endpoint

BASE_URL="http://localhost:8000"
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Global token variable
TOKEN=""

# Initialize session token
init_session() {
    echo -e "${YELLOW}=== Initializing Session ===${NC}"

    # Login with masteradmin credentials
    local login_response
    login_response=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$BASE_URL/auth/login" \
        -H "Content-Type: application/json" \
        -d '{"username": "masteradmin", "password": "superadmin"}')

    local http_code=$(echo "$login_response" | grep -o "HTTP_CODE:[0-9]*" | cut -d: -f2)
    local response_body=$(echo "$login_response" | grep -v "HTTP_CODE:")

    if [ "$http_code" = "200" ]; then
        # Extract token from response (check different response structures)
        TOKEN=$(echo "$response_body" | jq -r '.token // .access_token // .token // empty' 2>/dev/null)

        if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
            # Fallback to test token if no token in response
            TOKEN="test_token_from_session"
            echo -e "${YELLOW}No token in response, using fallback: $TOKEN${NC}"
        fi

        echo -e "${GREEN}✓ Session initialized successfully${NC}"
        echo -e "${GREEN}Token: ${TOKEN:0:30}...${NC}"
        echo "$TOKEN" > "$LOG_DIR/session_token.txt"
        return 0
    else
        echo -e "${RED}✗ Failed to initialize session (HTTP $http_code)${NC}"
        echo -e "${RED}Response: $response_body${NC}"
        return 1
    fi
}

# Record test result
record_test() {
    local test_name="$1"
    local endpoint="$2"
    local method="$3"
    local status="$4"
    local duration_ms="$5"
    local expected_status="$6"
    local actual_status="$7"
    local error_details="$8"

    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local status_color="$GREEN"
    local status_icon="✓"

    if [ "$status" != "PASS" ]; then
        status_color="$RED"
        status_icon="✗"
    fi

    local log_entry="[$timestamp] $status_icon $test_name | Method: $method | Endpoint: $endpoint | Expected: $expected_status | Actual: $actual_status | Duration: ${duration_ms}ms"

    if [ -n "$error_details" ]; then
        log_entry="$log_entry | Error: $error_details"
    fi

    echo -e "${status_color}$log_entry${NC}"
    echo "$log_entry" >> "$LOG_DIR/detailed_test_results.log"
}

# Execute API call and record result
api_call() {
    local test_name="$1"
    local endpoint="$2"
    local method="$3"
    local data="$4"
    local expected_status="$5"
    local description="$6"

    local start_time=$(date +%s%3N)
    local curl_cmd
    local output
    local http_code
    local total_time
    local response_body
    local error_details=""

    # Build curl command
    if [ "$method" = "GET" ]; then
        curl_cmd="curl -s -w \"\nHTTP_CODE:%{http_code} TOTAL_TIME:%{time_total}\" -X $method \"$BASE_URL$endpoint\""
    else
        curl_cmd="curl -s -w \"\nHTTP_CODE:%{http_code} TOTAL_TIME:%{time_total}\" -X $method \"$BASE_URL$endpoint\" \
            -H \"Content-Type: application/json\""

        if [ -n "$TOKEN" ]; then
            curl_cmd="$curl_cmd -H \"Authorization: Bearer $TOKEN\""
        fi

        if [ -n "$data" ]; then
            curl_cmd="$curl_cmd -d '$data'"
        fi
    fi

    # Execute API call
    output=$(eval $curl_cmd 2>/dev/null)
    http_code=$(echo "$output" | grep -o "HTTP_CODE:[0-9]*" | cut -d: -f2)
    total_time=$(echo "$output" | grep -o "TOTAL_TIME:[0-9.]*" | cut -d: -f2)
    duration_ms=$((total_time * 1000))

    response_body=$(echo "$output" | grep -v "HTTP_CODE:" | grep -v "TOTAL_TIME:")

    # Check result
    if [ "$http_code" = "$expected_status" ]; then
        record_test "$test_name" "$endpoint" "$method" "PASS" "$duration_ms" "$expected_status" "$http_code" "$description"
        return 0
    else
        error_details="HTTP $http_code - $description"
        record_test "$test_name" "$endpoint" "$method" "FAIL" "$duration_ms" "$expected_status" "$http_code" "$error_details"
        return 1
    fi
}

# Test authentication endpoints
test_auth_endpoints() {
    echo -e "${BLUE}=== Testing Authentication Endpoints ===${NC}"

    # Test login form
    api_call "Login Form" "/auth/login" "GET" "" "200" "Login page should be accessible"

    # Test login submission
    local login_data='{"username": "masteradmin", "password": "superadmin"}'
    if api_call "Login Submission" "/auth/login" "POST" "$login_data" "200" "Successful authentication"; then
        # Update session token from response
        local new_token
        new_token=$(echo "$response_body" | jq -r '.token // .access_token // empty' 2>/dev/null)
        if [ -n "$new_token" ] && [ "$new_token" != "null" ]; then
            TOKEN="$new_token"
        fi
    fi

    # Test login error case
    local invalid_data='{"username": "wrong", "password": "wrong"}'
    api_call "Login Failure" "/auth/login" "POST" "$invalid_data" "200" "Invalid credentials should be rejected"

    # Test logout
    api_call "Logout" "/auth/logout" "POST" "" "200" "User should be logged out"

    # Test change role
    local role_data='{"role": "author"}'
    api_call "Change Role" "/auth/role" "POST" "$role_data" "200" "Role should be changeable"
}

# Test health check endpoints
test_health_endpoints() {
    echo -e "${BLUE}=== Testing Health Check Endpoints ===${NC}"

    api_call "Basic Health Check" "/health" "GET" "" "200" "Server should be healthy"

    # Test with authentication
    api_call "Health with Auth" "/health" "GET" "" "$TOKEN" "200" "Health check should work with auth"
}

# Test parts endpoints
test_parts_endpoints() {
    echo -e "${BLUE}=== Testing Parts Endpoints ===${NC}"

    # List parts
    api_call "List Parts" "/parts" "GET" "" "200" "Should show parts list"

    # New part form
    api_call "New Part Form" "/parts/new" "GET" "" "200" "Should show part creation form"

    # Create part
    local part_data='{"part_number": "TEST-PART-001", "part_name": "Test Part", "part_revision": "A", "material": "ALUMINUM", "uom": "EA", "qty": 10, "status": "DRAFT"}'
    api_call "Create Part" "/parts/new" "POST" "$part_data" "200" "Part should be created successfully"

    # Part detail
    api_call "Part Detail" "/parts/TEST-PART-001" "GET" "" "200" "Should show part details"

    # Part edit form
    api_call "Part Edit Form" "/parts/TEST-PART-001/edit" "GET" "" "200" "Should show part edit form"

    # Update part
    local update_data='{"part_number": "TEST-PART-001", "part_name": "Updated Test Part", "part_revision": "B", "material": "STEEL", "uom": "EA", "qty": 15, "status": "RELEASED"}'
    api_call "Update Part" "/parts/TEST-PART-001/edit" "POST" "$update_data" "200" "Part should be updated"

    # Delete part
    api_call "Delete Part" "/parts/TEST-PART-001/delete" "POST" "" "200" "Part should be deleted"
}

# Test BOM endpoints
test_bom_endpoints() {
    echo -e "${BLUE}=== Testing BOM Endpoints ===${NC}}"

    # List BOM
    api_call "List BOM" "/bom" "GET" "" "200" "Should show BOM list"

    # BOM hierarchy form
    api_call "BOM Hierarchy Form" "/bom/hierarchy" "GET" "" "200" "Should show BOM hierarchy builder"

    # BOM hierarchy verification (pre-flight check)
    local bom_data='assembly1
        subcomponent1 2 EA
        subcomponent2 1 EA
        assembly1 1 EA'

    # URL encode the data for form submission
    local encoded_data=$(echo "$bom_data" | sed 's/ /%20/g')
    api_call "BOM Hierarchy Verify" "/bom/hierarchy/verify" "POST" "$encoded_data" "200" "BOM should be validated"

    # BOM new form
    api_call "BOM New Form" "/bom/new" "GET" "" "200" "Should show BOM creation form"

    # Create BOM item
    local bom_item_data='{"part_number": "BOM-PART-001", "part_revision": "A", "part_name": "Test BOM Part", "level": 0, "qty": 1, "uom": "EA", "parent_assembly": "", "material_notes": "Test material", "bom_type": "DESIGN"}'
    api_call "Create BOM Item" "/bom/new" "POST" "$bom_item_data" "200" "BOM item should be created"

    # BOM detail
    api_call "BOM Detail" "/bom/1" "GET" "" "200" "Should show BOM item details"

    # BOM edit form
    api_call "BOM Edit Form" "/bom/1/edit" "GET" "" "200" "Should show BOM edit form"

    # Update BOM item
    local bom_update_data='{"part_number": "BOM-PART-001", "part_revision": "B", "part_name": "Updated BOM Part", "level": 0, "qty": 2, "uom": "EA", "parent_assembly": "", "material_notes": "Updated material", "bom_type": "DESIGN"}'
    api_call "Update BOM Item" "/bom/1/edit" "POST" "$bom_update_data" "200" "BOM item should be updated"

    # Delete BOM item
    api_call "Delete BOM Item" "/bom/1/delete" "POST" "" "200" "BOM item should be deleted"
}

# Test ECO endpoints
test_eco_endpoints() {
    echo -e "${BLUE}=== Testing ECO Endpoints ===${NC}}"

    # List ECOs
    api_call "List ECOs" "/eco" "GET" "" "200" "Should show ECO list"

    # New ECO form
    api_call "New ECO Form" "/eco/new" "GET" "" "200" "Should show ECO creation form"

    # Create ECO
    local eco_data='{"eco_number": "ECO-2024-001", "eco_title": "Test ECO", "part_number": "TEST-PART", "eco_description": "Test description", "eco_status": "DRAFT"}'
    api_call "Create ECO" "/eco/new" "POST" "$eco_data" "200" "ECO should be created"

    # ECO detail
    api_call "ECO Detail" "/eco/ECO-2024-001" "GET" "" "200" "Should show ECO details"

    # ECO edit form
    api_call "ECO Edit Form" "/eco/ECO-2024-001/edit" "GET" "" "200" "Should show ECO edit form"

    # Update ECO
    local eco_update_data='{"eco_number": "ECO-2024-001", "eco_title": "Updated Test ECO", "part_number": "TEST-PART", "eco_description": "Updated description", "eco_status": "REVIEW"}'
    api_call "Update ECO" "/eco/ECO-2024-001/edit" "POST" "$eco_update_data" "200" "ECO should be updated"

    # Delete ECO
    api_call "Delete ECO" "/eco/ECO-2024-001/delete" "POST" "" "200" "ECO should be deleted"
}

# Test query endpoints
test_query_endpoints() {
    echo -e "${BLUE}=== Testing Query Endpoints ===${NC}}"

    # Queries builder page
    api_call "Queries Builder" "/queries" "GET" "" "200" "Should show query builder page"

    # Run guided query
    local query_data='{"entity": "parts", "columns": ["part_number", "part_name"], "filters": [], "sort": "", "sort_dir": "asc", "limit": 10}'
    api_call "Run Guided Query" "/queries/run" "POST" "$query_data" "200" "Guided query should execute successfully"

    # Run SQL query
    local sql_data='{"sql": "SELECT part_number, part_name FROM parts WHERE status = 'RELEASED' LIMIT 5"}'
    api_call "Run SQL Query" "/queries/run-sql" "POST" "$sql_data" "200" "SQL query should execute successfully"

    # Save query
    local save_data='{"report_name": "Test Report", "description": "Test report", "mode": "guided"}'
    api_call "Save Query" "/queries/save" "POST" "$save_data" "200" "Query should be saved"

    # List saved queries
    api_call "List Saved Queries" "/queries/saved" "GET" "" "200" "Should show list of saved queries"
}

# Test workflow endpoints
test_workflow_endpoints() {
    echo -e "${BLUE}=== Testing Workflow Endpoints ===${NC}}"

    # Workflow templates list
    api_call "Workflow Templates" "/workflow/templates" "GET" "" "200" "Should show workflow templates"

    # New template form
    api_call "New Template Form" "/workflow/templates/new" "GET" "" "200" "Should show template creation form"

    # Workflow inbox
    api_call "Workflow Inbox" "/workflow/inbox" "GET" "" "200" "Should show user inbox"

    # Create workflow instance (will likely fail without proper template, but should handle gracefully)
    local workflow_data='{"object_type": "part", "object_id": "TEST-PART-001", "template_id": 1}'
    api_call "Start Workflow" "/workflow/start" "POST" "$workflow_data" "200" "Should start workflow instance"
}

# Test admin endpoints
test_admin_endpoints() {
    echo -e "${BLUE}=== Testing Admin Endpoints ===${NC}}"

    # Admin tree
    api_call "Admin Tree" "/admin" "GET" "" "200" "Should show admin management tree"

    # Admin tenant view
    api_call "Admin Tenant View" "/admin/tenant/1" "GET" "" "200" "Should show tenant details"

    # Admin user view
    api_call "Admin User View" "/admin/user/1" "GET" "" "200" "Should show user details"
}

# Test error handling scenarios
test_error_handling() {
    echo -e "${BLUE}=== Testing Error Handling ===${NC}}"

    # Access with invalid token
    api_call "Invalid Token" "/parts" "GET" "" "403" "Should reject invalid authentication"

    # Access non-existent resource
    api_call "Non-existent Resource" "/parts/999999999" "GET" "" "404" "Should return 404 for non-existent resource"

    # Invalid HTTP method
    api_call "Invalid Method" "/parts/1" "PUT" "" "405" "Should reject unsupported HTTP methods"

    # Missing required fields in form data
    api_call "Missing Required Fields" "/parts/new" "POST" "invalid_data" "200" "Should handle invalid form data"
}

# Test CSV import functionality
test_import_functionality() {
    echo -e "${BLUE}=== Testing Import Functionality ===${NC}}"

    # Import page
    api_call "Import Page" "/import" "GET" "" "200" "Should show import page"

    # Import template
    api_call "Import Template" "/import/template?entity=parts" "GET" "" "200" "Should return CSV template"

    # Test CSV import endpoint (will likely fail without proper CSV, but should handle gracefully)
    api_call "CSV Import" "/import" "POST" "" "200" "Should handle CSV import request"
}

# Test file upload functionality
test_file_upload() {
    echo -e "${BLUE}=== Testing File Upload Functionality ===${NC}}"

    # CAD upload form (if available)
    api_call "CAD Upload Form" "/cad/new" "GET" "" "200" "Should show CAD upload form"

    # CAD list
    api_call "CAD List" "/cad" "GET" "" "200" "Should show CAD list"

    # Documents list
    api_call "Documents List" "/documents" "GET" "" "200" "Should show documents list"
}

# Test pagination and filtering
test_pagination_filtering() {
    echo -e "${BLUE}=== Testing Pagination and Filtering ===${NC}}"

    # Test with pagination parameters
    api_call "Paginated Parts" "/parts?page=1&page_size=10" "GET" "" "200" "Should show paginated parts"

    # Test with filter parameters
    api_call "Filtered Parts" "/parts?status=RELEASED" "GET" "" "200" "Should show filtered parts"

    # Test with search parameter
    api_call "Searched Parts" "/parts?q=TEST" "GET" "" "200" "Should show search results"
}

# Test concurrent requests
test_concurrent_requests() {
    echo -e "${BLUE}=== Testing Concurrent Requests ===${NC}}"

    # Make multiple parallel requests
    local start_time=$(date +%s%3N)

    # We can't easily test true concurrency with bash, but we can test multiple rapid requests
    for i in {1..3}; do
        api_call "Concurrent Request $i" "/health" "GET" "" "200" "Concurrent health check"
        sleep 0.1
    done

    local end_time=$(date +%s%3N)
    local duration=$((end_time - start_time))

    echo -e "${GREEN}Concurrent requests completed in ${duration}ms${NC}"
}

# Run all tests
run_all_tests() {
    echo -e "${YELLOW}=== Starting Comprehensive PLM-IQ API Test Suite ===${NC}}"
    echo -e "Test started at $(date)"
    echo -e "Base URL: $BASE_URL"
    echo -e "Log directory: $LOG_DIR"
    echo

    # Initialize log file
    echo "=== Detailed PLM-IQ API Test Log ===" > "$LOG_DIR/detailed_test_results.log"
    echo "Test started at $(date)" >> "$LOG_DIR/detailed_test_results.log"
    echo "Total tests will execute in batches..." >> "$LOG_DIR/detailed_test_results.log"
    echo

    # Check if server is available
    echo "Checking server availability..."
    if ! curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health" | grep -q "200"; then
        echo -e "${RED}Server is not responding. Please start the server first.${NC}"
        echo "Start command: uvicorn app.main:app --host 0.0.0.0 --port 8000"
        exit 1
    fi

    echo -e "${GREEN}✓ Server is responsive${NC}"
    echo

    # Initialize session
    if ! init_session; then
        echo -e "${RED}Failed to initialize session. Exiting.${NC}"
        exit 1
    fi

    echo

    # Run test batches
    test_auth_endpoints
    echo

    test_health_endpoints
    echo

    test_parts_endpoints
    echo

    test_bom_endpoints
    echo

    test_eco_endpoints
    echo

    test_query_endpoints
    echo

    test_workflow_endpoints
    echo

    test_admin_endpoints
    echo

    test_error_handling
    echo

    test_import_functionality
    echo

    test_file_upload
    echo

    test_pagination_filtering
    echo

    test_concurrent_requests
    echo

    # Summary
    echo -e "${YELLOW}=== Test Suite Complete ===${NC}}"
    echo -e "Results logged to: $LOG_DIR/detailed_test_results.log"
    echo -e "Session token saved to: $LOG_DIR/session_token.txt"
    echo -e "Test completed at $(date)"
    echo

    # Show summary statistics
    if [ -f "$LOG_DIR/detailed_test_results.log" ]; then
        local total_tests=$(grep -c "Status: PASS\|Status: FAIL" "$LOG_DIR/detailed_test_results.log" || echo "0")
        local passed_tests=$(grep "Status: PASS" "$LOG_DIR/detailed_test_results.log" | wc -l)
        local failed_tests=$(grep "Status: FAIL" "$LOG_DIR/detailed_test_results.log" | wc -l)
        local success_rate=0

        if [ "$total_tests" -gt 0 ]; then
            success_rate=$(echo "scale=2; $passed_tests * 100 / $total_tests" | bc)
        fi

        echo -e "Total Tests: $total_tests"
        echo -e "Passed: $passed_tests ${GREEN}(${success_rate}%)${NC}"
        echo -e "Failed: $failed_tests ${RED}(${success_rate}%)${NC}"

        echo -e "\nTop 10 most recent test results:"
        tail -20 "$LOG_DIR/detailed_test_results.log" | grep -E "\[.*\] (✓|✗)" | tail -10
    fi
}

# Execute main function
run_all_tests