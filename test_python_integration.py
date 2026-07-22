import requests
import time
import json
from datetime import datetime

class PLMiqAPITester:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.test_results = []
        self.start_time = datetime.now()

    def log_test(self, test_name, endpoint, method, status, duration, expected_status, actual_status, details=""):
        """Log test result with timing and status"""
        test_result = {
            'test_name': test_name,
            'endpoint': endpoint,
            'method': method,
            'status': status,
            'duration_ms': duration,
            'expected_status': expected_status,
            'actual_status': actual_status,
            'details': details,
            'timestamp': datetime.now().isoformat()
        }
        self.test_results.append(test_result)

        status_symbol = "✓" if status == "PASS" else "✗"
        color = "\033[0;32m" if status == "PASS" else "\033[0;31m"
        reset = "\033[0m"

        print(f"{color}{status_symbol} {test_name} | {method} {endpoint} | Expected: {expected_status} | Actual: {actual_status} | Duration: {duration}ms{reset}")

    def test_endpoint(self, test_name, endpoint, method="GET", data=None, expected_status=200, headers=None):
        """Test a single endpoint and record the result"""
        url = f"{self.base_url}{endpoint}"

        # Prepare headers
        request_headers = self.session.headers.copy()
        if headers:
            request_headers.update(headers)

        start_time = time.time()

        try:
            if method == "GET":
                response = self.session.get(url, headers=request_headers, params=data)
            elif method == "POST":
                response = self.session.post(url, headers=request_headers, json=data)
            elif method == "PUT":
                response = self.session.put(url, headers=request_headers, json=data)
            elif method == "DELETE":
                response = self.session.delete(url, headers=request_headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            end_time = time.time()
            duration_ms = int((end_time - start_time) * 1000)

            self.log_test(test_name, endpoint, method,
                         "PASS" if response.status_code == expected_status else "FAIL",
                         duration_ms, expected_status, response.status_code,
                         f"Response: {response.text[:200] if len(response.text) > 200 else response.text}")

            return response.status_code == expected_status, response

        except Exception as e:
            end_time = time.time()
            duration_ms = int((end_time - start_time) * 1000)
            self.log_test(test_name, endpoint, method, "FAIL", duration_ms, expected_status, "ERROR",
                         f"Exception: {str(e)}")
            return False, None

    def run_health_check(self):
        """Test basic health endpoint"""
        print("\n=== Health Check Tests ===")
        success, _ = self.test_endpoint("Basic Health Check", "/health", "GET", expected_status=200)
        return success

    def test_authentication(self):
        """Test authentication endpoints"""
        print("\n=== Authentication Tests ===")

        # Test login form
        success1, _ = self.test_endpoint("Login Form", "/auth/login", "GET", expected_status=200)

        # Test login submission
        login_data = {
            "username": "masteradmin",
            "password": "superadmin"
        }
        success2, response = self.test_endpoint("Login Submission", "/auth/login", "POST",
                                               login_data, expected_status=200)

        # Extract token from response if available
        if response and response.status_code == 200:
            try:
                if 'token' in response.json():
                    self.session.headers.update({"Authorization": f"Bearer {response.json()['token']}"})
                elif 'access_token' in response.json():
                    self.session.headers.update({"Authorization": f"Bearer {response.json()['access_token']}"})
            except:
                pass

        success3, _ = self.test_endpoint("Login Error Case", "/auth/login", "POST",
                                       {"username": "wrong", "password": "wrong"}, expected_status=200)

        return success1 and success2 and success3

    def test_parts_endpoints(self):
        """Test parts CRUD operations"""
        print("\n=== Parts Tests ===")

        # List parts
        success1, _ = self.test_endpoint("List Parts", "/parts", "GET", expected_status=200)

        # New part form
        success2, _ = self.test_endpoint("New Part Form", "/parts/new", "GET", expected_status=200)

        # Create part
        part_data = {
            "part_number": "TEST-PART-API-001",
            "part_name": "API Test Part",
            "part_revision": "A",
            "material": "ALUMINUM",
            "uom": "EA",
            "qty": 5,
            "status": "DRAFT",
            "tenant_id": 1
        }
        success3, response = self.test_endpoint("Create Part", "/parts/new", "POST",
                                               part_data, expected_status=200)

        created_part_id = "TEST-PART-API-001" if success3 else None

        # Part detail
        if created_part_id:
            success4, _ = self.test_endpoint("Part Detail", f"/parts/{created_part_id}", "GET", expected_status=200)

            # Part edit form
            success5, _ = self.test_endpoint("Part Edit Form", f"/parts/{created_part_id}/edit", "GET", expected_status=200)

            # Update part
            update_data = {
                "part_number": created_part_id,
                "part_name": "Updated API Test Part",
                "part_revision": "B",
                "material": "STEEL",
                "uom": "EA",
                "qty": 10,
                "status": "RELEASED",
                "tenant_id": 1
            }
            success6, _ = self.test_endpoint("Update Part", f"/parts/{created_part_id}/edit", "POST",
                                           update_data, expected_status=200)

            # Delete part
            success7, _ = self.test_endpoint("Delete Part", f"/parts/{created_part_id}/delete", "POST", expected_status=200)

            return success1 and success2 and success3 and success4 and success5 and success6 and success7
        else:
            return success1 and success2 and success3

    def test_bom_endpoints(self):
        """Test BOM endpoints"""
        print("\n=== BOM Tests ===")

        success1, _ = self.test_endpoint("List BOM", "/bom", "GET", expected_status=200)
        success2, _ = self.test_endpoint("BOM Hierarchy Form", "/bom/hierarchy", "GET", expected_status=200)

        return success1 and success2

    def test_query_endpoints(self):
        """Test query builder endpoints"""
        print("\n=== Query Tests ===")

        success1, _ = self.test_endpoint("Queries Builder", "/queries", "GET", expected_status=200)

        # Test guided query
        query_data = {
            "entity": "parts",
            "columns": ["part_number", "part_name"],
            "filters": [],
            "sort": "",
            "sort_dir": "asc",
            "limit": 5
        }
        success2, _ = self.test_endpoint("Run Guided Query", "/queries/run", "POST",
                                       query_data, expected_status=200)

        # Test SQL query
        sql_data = {
            "sql": "SELECT COUNT(*) FROM parts"
        }
        success3, _ = self.test_endpoint("Run SQL Query", "/queries/run-sql", "POST",
                                       sql_data, expected_status=200)

        return success1 and success2 and success3

    def run_all_tests(self):
        """Run all test suites"""
        print("=" * 60)
        print("PLM-IQ API Integration Test Suite")
        print("=" * 60)
        print(f"Starting tests at {self.start_time}")
        print(f"Base URL: {self.base_url}")

        # Check if server is available
        print("\nChecking server availability...")
        try:
            response = requests.get(f"{self.base_url}/health")
            if response.status_code != 200:
                print(f"Server health check failed: {response.status_code}")
                return False
            print("✓ Server is responsive")
        except Exception as e:
            print(f"✗ Server is not accessible: {str(e)}")
            print("Please ensure the server is running with:")
            print("uvicorn app.main:app --host 0.0.0.0 --port 8000")
            return False

        # Run test suites
        health_ok = self.run_health_check()
        auth_ok = self.test_authentication()
        parts_ok = self.test_parts_endpoints()
        bom_ok = self.test_bom_endpoints()
        query_ok = self.test_query_endpoints()

        end_time = datetime.now()
        total_duration = int((end_time - self.start_time).total_seconds() * 1000)

        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"Total duration: {total_duration}ms")
        print(f"Health tests: {'PASS' if health_ok else 'FAIL'}")
        print(f"Authentication tests: {'PASS' if auth_ok else 'FAIL'}")
        print(f"Parts tests: {'PASS' if parts_ok else 'FAIL'}")
        print(f"BOM tests: {'PASS' if bom_ok else 'FAIL'}")
        print(f"Query tests: {'PASS' if query_ok else 'FAIL'}")

        overall_success = health_ok and auth_ok and parts_ok and bom_ok and query_ok

        if overall_success:
            print("\n✓ OVERALL RESULT: ALL TESTS PASSED")
        else:
            print("\n✗ OVERALL RESULT: SOME TESTS FAILED")

        # Save detailed results
        self.save_results(total_duration, overall_success)

        return overall_success

    def save_results(self, total_duration, overall_success):
        """Save detailed test results to file"""
        results = {
            'test_suite': 'PLM-IQ API Integration Tests',
            'start_time': self.start_time.isoformat(),
            'end_time': datetime.now().isoformat(),
            'total_duration_ms': total_duration,
            'overall_success': overall_success,
            'test_results': self.test_results
        }

        # Generate statistics
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r['status'] == 'PASS'])
        failed_tests = len([r for r in self.test_results if r['status'] == 'FAIL'])

        if total_tests > 0:
            success_rate = (passed_tests / total_tests) * 100
        else:
            success_rate = 0

        results['statistics'] = {
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': failed_tests,
            'success_rate_percent': round(success_rate, 2)
        }

        # Save to JSON file
        with open('test_results.json', 'w') as f:
            json.dump(results, f, indent=2)

        # Also save a summary log
        with open('test_summary.log', 'w') as f:
            f.write("PLM-IQ API Integration Test Summary\n")
            f.write("=" * 50 + "\n")
            f.write(f"Total tests: {total_tests}\n")
            f.write(f"Passed: {passed_tests} ({success_rate:.2f}%)\n")
            f.write(f"Failed: {failed_tests} ({100 - success_rate:.2f}%)\n")
            f.write(f"\nDetailed results saved to: test_results.json\n")
            f.write("\nRecent test results:\n")
            for result in self.test_results[-10:]:  # Last 10 tests
                f.write(f"  {result['test_name']} - {result['status']} - {result['duration_ms']}ms\n")

        print(f"\nResults saved to: test_results.json and test_summary.log")

if __name__ == "__main__":
    tester = PLMiqAPITester()
    success = tester.run_all_tests()
    exit(0 if success else 1)