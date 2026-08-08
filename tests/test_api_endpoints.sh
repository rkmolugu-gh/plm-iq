#!/bin/bash

# Comprehensive API Test Script for PLM-IQ
# Tests all major endpoints with detailed logging, timing, and error handling

BASE_URL="http://localhost:8000"
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log_result() {
    local test_name="$1"
    local status="$2"
    local duration="$3"
    local endpoint="$4"
    local details="$5"

    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local log_entry="[$timestamp] $test_name | Status: $status | Duration: ${duration}ms | Endpoint: $endpoint | Details: $details"

    echo -e "$log_entry"

    # Log to file
    echo "$log_entry" >> "$LOG_DIR/test_results.log"
}

# Execute curl command with timing and error handling
test_endpoint() {
    local test_name="$1"
    local method="$2"
    local endpoint="$3"
    local data="$4"
    local token="$5"
    local expected_status="$6"

    local start_time=$(date +%s%3N)

    # Prepare curl command
    local curl_cmd="curl -s -w \"\nHTTP_CODE:%{http_code} TOTAL_TIME:%{time_total}\" -X $method"

    if [ "$token" != "" ]; then
        curl_cmd="$curl_cmd -H \"Authorization: Bearer $token\""
    fi

    if [ "$data" != "" ]; then
        curl_cmd="$curl_cmd -H \"Content-Type: application/json\" -d '$data'"
    fi

    curl_cmd="$curl_cmd \"$BASE_URL$endpoint\""

    # Execute command
    local output
    local http_code
    local total_time

    output=$(eval $curl_cmd 2>/dev/null)
    http_code=$(echo "$output" | grep -o "HTTP_CODE:[0-9]*" | cut -d: -f2)
    total_time=$(echo "$output" | grep -o "TOTAL_TIME:[0-9.]*" | cut -d: -f2)

    # Convert total_time to milliseconds
    duration=$((total_time * 1000))

    # Extract response body (remove curl output)
    response_body=$(echo "$output" | grep -v "HTTP_CODE:" | grep -v "TOTAL_TIME:")

    local status
    local details

    if [ "$http_code" = "$expected_status" ]; then
        status="PASS"
        details="Expected: $expected_status, Got: $http_code"
        echo -e "${GREEN}[PASS]${NC} $test_name - ${duration}ms - $endpoint ($details)"
    else
        status="FAIL"
        details="Expected: $expected_status, Got: $http_code - Response: $response_body"
        echo -e "${RED}[FAIL]${NC} $test_name - ${duration}ms - $endpoint ($details)"
    fi

    log_result "$test_name" "$status" "$duration" "$endpoint" "$details"
}

# Test helper to get authentication token
test_authentication() {
    echo -e "${YELLOW}=== Testing Authentication ===${NC}"

    # Test login
    local login_data='{"username": "masteradmin", "password": "superadmin"}'

    local output
    local http_code
    local total_time

    local start_time=$(date +%s%3N)

    output=$(curl -s -w "\nHTTP_CODE:%{http_code} TOTAL_TIME:%{time_total}" -X POST "$BASE_URL/auth/login" \
        -H "Content-Type: application/json" -d "$login_data")

    http_code=$(echo "$output" | grep -o "HTTP_CODE:[0-9]*" | cut -d: -f2)
    total_time=$(echo "$output" | grep -o "TOTAL_TIME:[0-9.]*" | cut -d: -f2)

    if [ "$http_code" = "200" ]; then
        # Extract token from response
        token=$(echo "$output" | grep -v "HTTP_CODE:" | grep -v "TOTAL_TIME:" | jq -r '.token // .access_token // .token\" 2>/dev/null || echo "test_token"')

        # Test token validation
        test_endpoint "Health Check with Auth" "GET" "/health" "" "$token" "200"

        log_result "Authentication" "PASS" "$((total_time * 1000))" "/auth/login" "Token obtained: ${token:0:20}..."
        echo -e "${GREEN}Authentication token: $token${NC}"

        echo "$token" > "$LOG_DIR/auth_token.txt"
        return 0
    else
        log_result "Authentication" "FAIL" "$((total_time * 1000))" "/auth/login" "Got HTTP $http_code"
        echo -e "${RED}Authentication failed with HTTP $http_code${NC}"
        return 1
    fi
}

# Test basic CRUD operations for a resource
test_resource_crud() {
    local resource_name="$1"
    local token="$2"

    echo -e "${YELLOW}=== Testing $resource_name CRUD ===${NC}"

    # Test list endpoint
    test_endpoint "$resource_name List" "GET" "/$resource_name" "" "$token" "200"

    # Test create endpoint (if supported)
    if [[ "$resource_name" == "parts" ]]; then
        local create_data='{"part_number": "TEST-PART-001", "part_name": "Test Part", "part_revision": "A", "material": "ALUM", "uom": "EA", "qty": 1, "status": "DRAFT", "tenant_id": 1}'
        test_endpoint "$resource_name Create" "POST" "/$resource_name/new" "$create_data" "$token" "200"

        # Extract created ID and test detail/edit/delete
        local create_output
        create_output=$(curl -s -X POST "$BASE_URL/$resource_name/new" \
            -H "Authorization: Bearer $token" -H "Content-Type: application/json" -d "$create_data")

        # Test detail endpoint
        test_endpoint "$resource_name Detail" "GET" "/$resource_name/TEST-PART-001" "" "$token" "200"

        # Test edit endpoint
        test_endpoint "$resource_name Edit Form" "GET" "/$resource_name/TEST-PART-001/edit" "" "$token" "200"

        local update_data='{"part_number": "TEST-PART-001", "part_name": "Updated Test Part", "part_revision": "B", "material": "STEEL", "uom": "EA", "qty": 2, "status": "RELEASED", "tenant_id": 1}'
        test_endpoint "$resource_name Update" "POST" "/$resource_name/TEST-PART-001/edit" "$update_data" "$token" "200"

        # Test delete endpoint
        test_endpoint "$resource_name Delete" "POST" "/$resource_name/TEST-PART-001/delete" "" "$token" "200"
    fi
}

# Test specialized endpoints with file uploads
test_specialized_endpoints() {
    local token="$1"

    echo -e "${YELLOW}=== Testing Specialized Endpoints ===${NC}"

    # Test BOM hierarchy endpoints
    test_endpoint "BOM List" "GET" "/bom" "" "$token" "200"
    test_endpoint "BOM Hierarchy Form" "GET" "/bom/hierarchy" "" "$token" "200"

    # Test import endpoints
    test_endpoint "Import Page" "GET" "/import" "" "$token" "200"
    test_endpoint "Import Template" "GET" "/import/template?entity=parts" "" "$token" "200"

    # Test workflow endpoints
    test_endpoint "Workflow Definitions" "GET" "/workflow/templates" "" "$token" "200"
    test_endpoint "Workflow Inbox" "GET" "/workflow/inbox" "" "$token" "200"

    # Test admin endpoints
    test_endpoint "Admin Tree" "GET" "/admin" "" "$token" "200"
    test_endpoint "Admin Tenant View" "GET" "/admin/tenant/1" "" "$token" "200"
}

# Test error handling endpoints
test_error_scenarios() {
    local token="$1"

    echo -e "${YELLOW}=== Testing Error Scenarios ===${NC}"

    # Test accessing non-existent resource
    test_endpoint "Non-existent Resource" "GET" "/parts/999999" "" "$token" "404"

    # Test missing authentication
    test_endpoint "Unauthenticated Request" "GET" "/parts" "" "" "200"  # Should redirect to login

    # Test invalid HTTP method
    test_endpoint "Invalid Method" "POST" "/parts" "invalid_data" "$token" "405"
}

# Test database-heavy endpoints that require valid data
test_data_heavy_endpoints() {
    local token=""$1"

    echo -e "${YELLOW}=== Testing Data-Heavy Endpoints ===${NC}"

    # Test dashboard with statistics
    test_endpoint "Dashboard" "GET" "/" "" "$token" "200"

    # Test queries builder
    test_endpoint "Queries Builder" "GET" "/queries" "" "$token" "200"

    # Test documents listing
    test_endpoint "Documents List" "GET" "/documents" "" "$token" "200"
}

# Main test execution
main() {
    echo -e "${BLUE}=== PLM-IQ API Comprehensive Test Suite ===${NC}"
    echo -e "Test started at $(date)"
    echo -e "Base URL: $BASE_URL"
    echo -e "Log directory: $LOG_DIR"
    echo

    # Initialize log file
    echo "=== PLM-IQ API Test Log ===" > "$LOG_DIR/test_results.log"
    echo "Test started at $(date)" >> "$LOG_DIR/test_results.log"

    # Check if server is running
    echo "Checking server availability..."
    if ! curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health" | grep -q "200"; then
        echo -e "${RED}Server is not responding. Please start the server first.${NC}"
        echo "Start command: uvicorn app.main:app --host 0.0.0.0 --port 8000"
        exit 1
    fi

    echo -e "${GREEN}Server is responsive${NC}"
    echo

    # Run authentication test
    if ! test_authentication; then
        echo -e "${RED}Authentication test failed. Exiting.${NC}"
        exit 1
    fi

    echo

    # Test main resource types
    test_resource_crud "parts" "$token"
    test_resource_crud "bom" "$token"
    test_resource_crud "eco" "$token"
    test_resource_crud "costing" "$token"
    test_resource_crud "aml" "$token"
    test_resource_crud "avl" "$token"

    echo

    # Test specialized endpoints
    test_specialized_endpoints "$token"

    echo

    # Test error scenarios
    test_error_scenarios "$token"

    echo

    # Test data-heavy endpoints
    test_data_heavy_endpoints "$token"

    echo

    # Summary
    echo -e "${BLUE}=== Test Summary ===${NC}"
    echo -e "Results logged to: $LOG_DIR/test_results.log"
    echo -e "Token saved to: $LOG_DIR/auth_token.txt"
    echo -e "Test completed at $(date)"
    echo

    # Show summary statistics
    if [ -f "$LOG_DIR/test_results.log" ]; then
        local total_tests=$(grep -c "Test:" "$LOG_DIR/test_results.log" || echo "0")
        local passed_tests=$(grep "Status: PASS" "$LOG_DIR/test_results.log" | wc -l)
        local failed_tests=$(grep "Status: FAIL" "$LOG_DIR/test_results.log" | wc -l)
        local success_rate=0

        if [ "$total_tests" -gt 0 ]; then
            success_rate=$(echo "scale=2; $passed_tests * 100 / $total_tests" | bc)
        fi

        echo -e "Total Tests: $total_tests"
        echo -e "Passed: $passed_tests ${GREEN}(${success_rate}%)${NC}"
        echo -e "Failed: $failed_tests ${RED}(${success_rate}%)${NC}"
    fi
}

# Execute main function
main