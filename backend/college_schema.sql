-- =============================================================================
-- college_schema.sql
-- Full college database schema with dummy data
-- Tables: departments, professors, courses, students, enrollments,
--         exams, exam_results, library_books, book_issues, hostels
-- =============================================================================

-- Drop in reverse dependency order
DROP TABLE IF EXISTS book_issues      CASCADE;
DROP TABLE IF EXISTS library_books    CASCADE;
DROP TABLE IF EXISTS exam_results     CASCADE;
DROP TABLE IF EXISTS exams            CASCADE;
DROP TABLE IF EXISTS enrollments      CASCADE;
DROP TABLE IF EXISTS courses          CASCADE;
DROP TABLE IF EXISTS students         CASCADE;
DROP TABLE IF EXISTS professors       CASCADE;
DROP TABLE IF EXISTS hostels          CASCADE;
DROP TABLE IF EXISTS departments      CASCADE;

-- =============================================================================
-- 1. DEPARTMENTS
-- =============================================================================
CREATE TABLE departments (
    department_id   SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL UNIQUE,
    code            VARCHAR(10)  NOT NULL UNIQUE,
    building        VARCHAR(50),
    established_year INT,
    hod_name        VARCHAR(100)
);

INSERT INTO departments (name, code, building, established_year, hod_name) VALUES
  ('Computer Science',       'CS',   'Tech Block A',    1990, 'Dr. Ramesh Sharma'),
  ('Electronics Engineering','EC',   'Tech Block B',    1985, 'Dr. Priya Nair'),
  ('Mechanical Engineering', 'ME',   'Workshop Block',  1980, 'Dr. Suresh Patel'),
  ('Civil Engineering',      'CE',   'Design Block',    1978, 'Dr. Anita Singh'),
  ('Mathematics',            'MATH', 'Science Block',   1975, 'Dr. Vijay Kumar'),
  ('Physics',                'PHY',  'Science Block',   1975, 'Dr. Kavita Rao'),
  ('MBA',                    'MBA',  'Admin Block',     2000, 'Dr. Deepak Mehta');

-- =============================================================================
-- 2. HOSTELS
-- =============================================================================
CREATE TABLE hostels (
    hostel_id   SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    type        VARCHAR(10)  NOT NULL CHECK (type IN ('boys', 'girls')),
    capacity    INT NOT NULL,
    warden_name VARCHAR(100)
);

INSERT INTO hostels (name, type, capacity, warden_name) VALUES
  ('Tagore Bhawan',    'boys',  200, 'Mr. Ramakant Joshi'),
  ('Saraswati Bhawan', 'girls', 150, 'Mrs. Sunita Verma'),
  ('Vivekananda Niwas','boys',  180, 'Mr. Prakash Tiwari'),
  ('Laxmi Bhawan',     'girls', 120, 'Mrs. Annapurna Das');

-- =============================================================================
-- 3. PROFESSORS
-- =============================================================================
CREATE TABLE professors (
    professor_id    SERIAL PRIMARY KEY,
    first_name      VARCHAR(50)  NOT NULL,
    last_name       VARCHAR(50)  NOT NULL,
    email           VARCHAR(100) NOT NULL UNIQUE,
    phone           VARCHAR(15),
    department_id   INT NOT NULL REFERENCES departments(department_id),
    designation     VARCHAR(50)  NOT NULL,  -- Professor / Assoc. Professor / Asst. Professor
    salary          NUMERIC(10,2),
    joining_date    DATE NOT NULL,
    specialization  VARCHAR(100)
);

INSERT INTO professors (first_name, last_name, email, phone, department_id, designation, salary, joining_date, specialization) VALUES
  ('Ramesh',  'Sharma',   'ramesh.sharma@college.edu',   '9812345601', 1, 'Professor',           95000, '2005-07-01', 'Machine Learning'),
  ('Anjali',  'Gupta',    'anjali.gupta@college.edu',    '9812345602', 1, 'Associate Professor', 78000, '2010-01-15', 'Database Systems'),
  ('Vikram',  'Joshi',    'vikram.joshi@college.edu',    '9812345603', 1, 'Assistant Professor', 62000, '2018-06-01', 'Web Technologies'),
  ('Priya',   'Nair',     'priya.nair@college.edu',      '9812345604', 2, 'Professor',           92000, '2004-08-01', 'VLSI Design'),
  ('Sanjay',  'Mehta',    'sanjay.mehta@college.edu',    '9812345605', 2, 'Associate Professor', 76000, '2011-03-01', 'Embedded Systems'),
  ('Suresh',  'Patel',    'suresh.patel@college.edu',    '9812345606', 3, 'Professor',           90000, '2003-07-01', 'Thermodynamics'),
  ('Neha',    'Desai',    'neha.desai@college.edu',      '9812345607', 3, 'Assistant Professor', 60000, '2019-07-01', 'CAD/CAM'),
  ('Anita',   'Singh',    'anita.singh@college.edu',     '9812345608', 4, 'Professor',           88000, '2006-01-01', 'Structural Engineering'),
  ('Vijay',   'Kumar',    'vijay.kumar@college.edu',     '9812345609', 5, 'Professor',           85000, '2002-07-01', 'Linear Algebra'),
  ('Kavita',  'Rao',      'kavita.rao@college.edu',      '9812345610', 6, 'Professor',           83000, '2007-01-01', 'Quantum Physics'),
  ('Deepak',  'Mehta',    'deepak.mehta@college.edu',    '9812345611', 7, 'Professor',           98000, '2001-07-01', 'Marketing Strategy'),
  ('Sunita',  'Iyer',     'sunita.iyer@college.edu',     '9812345612', 7, 'Associate Professor', 75000, '2012-06-01', 'Finance');

-- =============================================================================
-- 4. COURSES
-- =============================================================================
CREATE TABLE courses (
    course_id       SERIAL PRIMARY KEY,
    code            VARCHAR(15)  NOT NULL UNIQUE,
    name            VARCHAR(150) NOT NULL,
    department_id   INT NOT NULL REFERENCES departments(department_id),
    professor_id    INT          REFERENCES professors(professor_id),
    credits         INT NOT NULL DEFAULT 3,
    semester        INT NOT NULL CHECK (semester BETWEEN 1 AND 8),
    max_students    INT NOT NULL DEFAULT 60
);

INSERT INTO courses (code, name, department_id, professor_id, credits, semester, max_students) VALUES
  ('CS101',  'Introduction to Programming',       1, 3,  4, 1, 80),
  ('CS201',  'Data Structures & Algorithms',      1, 1,  4, 2, 70),
  ('CS301',  'Database Management Systems',       1, 2,  3, 3, 60),
  ('CS401',  'Machine Learning',                  1, 1,  4, 5, 50),
  ('CS402',  'Web Development',                   1, 3,  3, 5, 60),
  ('EC101',  'Basic Electronics',                 2, 4,  4, 1, 75),
  ('EC301',  'VLSI Design',                       2, 4,  3, 4, 40),
  ('EC302',  'Embedded Systems',                  2, 5,  3, 4, 45),
  ('ME101',  'Engineering Drawing',               3, 6,  3, 1, 80),
  ('ME301',  'Thermodynamics',                    3, 6,  4, 3, 65),
  ('CE301',  'Structural Analysis',               4, 8,  4, 3, 55),
  ('MATH101','Engineering Mathematics I',         5, 9,  4, 1, 100),
  ('MATH201','Engineering Mathematics II',        5, 9,  4, 2, 100),
  ('PHY101', 'Engineering Physics',               6, 10, 4, 1, 100),
  ('MBA501', 'Marketing Management',              7, 11, 3, 1, 60),
  ('MBA502', 'Financial Management',              7, 12, 3, 1, 60);

-- =============================================================================
-- 5. STUDENTS
-- =============================================================================
CREATE TABLE students (
    student_id      SERIAL PRIMARY KEY,
    roll_number     VARCHAR(20)  NOT NULL UNIQUE,
    first_name      VARCHAR(50)  NOT NULL,
    last_name       VARCHAR(50)  NOT NULL,
    email           VARCHAR(100) NOT NULL UNIQUE,
    phone           VARCHAR(15),
    date_of_birth   DATE,
    gender          VARCHAR(10) CHECK (gender IN ('male', 'female', 'other')),
    department_id   INT NOT NULL REFERENCES departments(department_id),
    current_semester INT NOT NULL DEFAULT 1,
    admission_year  INT NOT NULL,
    hostel_id       INT REFERENCES hostels(hostel_id),
    city            VARCHAR(50),
    state           VARCHAR(50),
    cgpa            NUMERIC(4,2)
);

INSERT INTO students (roll_number, first_name, last_name, email, phone, date_of_birth, gender, department_id, current_semester, admission_year, hostel_id, city, state, cgpa) VALUES
  ('CS2021001', 'Arjun',    'Sharma',   'arjun.sharma@student.edu',   '9900001001', '2003-05-12', 'male',   1, 5, 2021, 1, 'Delhi',     'Delhi',          8.75),
  ('CS2021002', 'Sneha',    'Patel',    'sneha.patel@student.edu',    '9900001002', '2003-08-22', 'female', 1, 5, 2021, 2, 'Mumbai',    'Maharashtra',    9.10),
  ('CS2021003', 'Rohit',    'Kumar',    'rohit.kumar@student.edu',    '9900001003', '2002-11-30', 'male',   1, 5, 2021, 1, 'Patna',     'Bihar',          7.40),
  ('CS2022001', 'Ananya',   'Gupta',    'ananya.gupta@student.edu',   '9900001004', '2004-02-14', 'female', 1, 3, 2022, 2, 'Jaipur',    'Rajasthan',      8.50),
  ('CS2022002', 'Karan',    'Verma',    'karan.verma@student.edu',    '9900001005', '2004-06-10', 'male',   1, 3, 2022, 1, 'Lucknow',   'Uttar Pradesh',  7.80),
  ('EC2021001', 'Pooja',    'Nair',     'pooja.nair@student.edu',     '9900001006', '2003-03-18', 'female', 2, 5, 2021, 2, 'Kochi',     'Kerala',         8.90),
  ('EC2021002', 'Rahul',    'Menon',    'rahul.menon@student.edu',    '9900001007', '2003-07-25', 'male',   2, 5, 2021, 1, 'Thrissur',  'Kerala',         8.20),
  ('EC2022001', 'Divya',    'Krishnan', 'divya.krishnan@student.edu', '9900001008', '2004-01-05', 'female', 2, 3, 2022, 2, 'Chennai',   'Tamil Nadu',     7.95),
  ('ME2021001', 'Suraj',    'Singh',    'suraj.singh@student.edu',    '9900001009', '2003-09-15', 'male',   3, 5, 2021, 1, 'Bhopal',    'MP',             7.30),
  ('ME2021002', 'Priyanka', 'Yadav',    'priyanka.yadav@student.edu', '9900001010', '2003-12-28', 'female', 3, 5, 2021, 2, 'Indore',    'MP',             8.10),
  ('CE2021001', 'Aditya',   'Mishra',   'aditya.mishra@student.edu',  '9900001011', '2002-04-03', 'male',   4, 5, 2021, 1, 'Varanasi',  'Uttar Pradesh',  7.60),
  ('CE2022001', 'Meera',    'Joshi',    'meera.joshi@student.edu',    '9900001012', '2004-08-19', 'female', 4, 3, 2022, 2, 'Pune',      'Maharashtra',    8.30),
  ('MBA2022001','Vikas',    'Agarwal',  'vikas.agarwal@student.edu',  '9900001013', '2001-06-07', 'male',   7, 1, 2022, NULL,'Ahmedabad', 'Gujarat',       7.50),
  ('MBA2022002','Ritu',     'Bose',     'ritu.bose@student.edu',      '9900001014', '2001-10-20', 'female', 7, 1, 2022, NULL,'Kolkata',   'West Bengal',   8.80),
  ('CS2023001', 'Harshit',  'Tiwari',   'harshit.tiwari@student.edu', '9900001015', '2005-01-11', 'male',   1, 1, 2023, 1, 'Raipur',    'Chhattisgarh',   NULL),
  ('CS2023002', 'Ankita',   'Dubey',    'ankita.dubey@student.edu',   '9900001016', '2005-03-29', 'female', 1, 1, 2023, 2, 'Bilaspur',  'Chhattisgarh',   NULL);

-- =============================================================================
-- 6. ENROLLMENTS  (student ↔ course join)
-- =============================================================================
CREATE TABLE enrollments (
    enrollment_id   SERIAL PRIMARY KEY,
    student_id      INT NOT NULL REFERENCES students(student_id),
    course_id       INT NOT NULL REFERENCES courses(course_id),
    enrolled_on     DATE NOT NULL DEFAULT CURRENT_DATE,
    status          VARCHAR(20) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','dropped','completed')),
    UNIQUE (student_id, course_id)
);

INSERT INTO enrollments (student_id, course_id, enrolled_on, status) VALUES
  -- CS 2021 batch (semester 5 courses + earlier completed)
  (1, 4, '2023-07-10', 'active'),   -- Arjun → ML
  (1, 5, '2023-07-10', 'active'),   -- Arjun → Web Dev
  (1, 2, '2022-01-05', 'completed'),-- Arjun → DSA
  (1, 3, '2022-07-08', 'completed'),-- Arjun → DBMS
  (2, 4, '2023-07-10', 'active'),   -- Sneha → ML
  (2, 5, '2023-07-10', 'active'),   -- Sneha → Web Dev
  (2, 2, '2022-01-05', 'completed'),-- Sneha → DSA
  (3, 4, '2023-07-10', 'active'),   -- Rohit → ML
  (3, 5, '2023-07-10', 'active'),   -- Rohit → Web Dev
  -- CS 2022 batch (semester 3)
  (4, 2, '2023-01-09', 'active'),   -- Ananya → DSA
  (4, 3, '2023-01-09', 'active'),   -- Ananya → DBMS
  (5, 2, '2023-01-09', 'active'),   -- Karan → DSA
  (5, 3, '2023-01-09', 'active'),   -- Karan → DBMS
  -- EC students
  (6, 7, '2023-07-10', 'active'),   -- Pooja → VLSI
  (6, 8, '2023-07-10', 'active'),   -- Pooja → Embedded
  (7, 7, '2023-07-10', 'active'),   -- Rahul → VLSI
  (8, 6, '2023-01-09', 'active'),   -- Divya → Basic Electronics (sem 1 catch-up)
  -- ME students
  (9,  10, '2023-07-10', 'active'), -- Suraj → Thermodynamics
  (10, 10, '2023-07-10', 'active'), -- Priyanka → Thermodynamics
  -- CE student
  (11, 11, '2023-07-10', 'active'), -- Aditya → Structural Analysis
  (12, 11, '2023-01-09', 'active'), -- Meera → Structural Analysis
  -- MBA students
  (13, 15, '2022-08-01', 'active'), -- Vikas → Marketing
  (13, 16, '2022-08-01', 'active'), -- Vikas → Finance
  (14, 15, '2022-08-01', 'active'), -- Ritu → Marketing
  (14, 16, '2022-08-01', 'active'), -- Ritu → Finance
  -- New 2023 batch
  (15, 1,  '2023-08-01', 'active'), -- Harshit → Intro to Programming
  (16, 1,  '2023-08-01', 'active'); -- Ankita → Intro to Programming

-- =============================================================================
-- 7. EXAMS
-- =============================================================================
CREATE TABLE exams (
    exam_id     SERIAL PRIMARY KEY,
    course_id   INT NOT NULL REFERENCES courses(course_id),
    exam_type   VARCHAR(30) NOT NULL CHECK (exam_type IN ('mid_term','end_term','quiz','assignment')),
    exam_date   DATE NOT NULL,
    total_marks INT NOT NULL DEFAULT 100,
    duration_mins INT
);

INSERT INTO exams (course_id, exam_type, exam_date, total_marks, duration_mins) VALUES
  (1,  'mid_term',  '2023-09-20', 50,  90),
  (1,  'end_term',  '2023-11-25', 100, 180),
  (2,  'mid_term',  '2023-09-22', 50,  90),
  (2,  'end_term',  '2023-11-28', 100, 180),
  (3,  'mid_term',  '2023-09-25', 50,  90),
  (3,  'end_term',  '2023-11-30', 100, 180),
  (4,  'mid_term',  '2023-09-18', 50,  90),
  (4,  'end_term',  '2023-11-22', 100, 180),
  (5,  'mid_term',  '2023-09-19', 50,  90),
  (10, 'mid_term',  '2023-09-21', 50,  90),
  (15, 'end_term',  '2023-11-20', 100, 180),
  (16, 'end_term',  '2023-11-21', 100, 180);

-- =============================================================================
-- 8. EXAM RESULTS  (student ↔ exam join)
-- =============================================================================
CREATE TABLE exam_results (
    result_id   SERIAL PRIMARY KEY,
    student_id  INT NOT NULL REFERENCES students(student_id),
    exam_id     INT NOT NULL REFERENCES exams(exam_id),
    marks_obtained NUMERIC(5,2) NOT NULL,
    grade       VARCHAR(5),
    UNIQUE (student_id, exam_id)
);

INSERT INTO exam_results (student_id, exam_id, marks_obtained, grade) VALUES
  -- Arjun (CS2021001)
  (1, 3, 42, 'A'),  (1, 4, 85, 'A'),  (1, 5, 38, 'B+'),
  (1, 6, 80, 'A'),  (1, 7, 44, 'A+'), (1, 8, 92, 'A+'),
  -- Sneha (CS2021002)
  (2, 3, 48, 'A+'), (2, 4, 95, 'A+'), (2, 7, 47, 'A+'), (2, 8, 96, 'A+'),
  -- Rohit (CS2021003)
  (3, 7, 35, 'B'),  (3, 8, 70, 'B+'),
  -- Ananya (CS2022001)
  (4, 3, 45, 'A'),  (4, 5, 40, 'A'),
  -- Karan (CS2022002)
  (5, 3, 38, 'B+'), (5, 5, 32, 'B'),
  -- Pooja (EC2021001)
  (6, 1, 44, 'A'),  (6, 2, 88, 'A'),
  -- Suraj (ME2021001)
  (9,  10, 37, 'B+'),(9,  11, 72, 'B+'),
  -- Priyanka (ME2021002)
  (10, 10, 41, 'A'), (10, 11, 84, 'A'),
  -- Vikas (MBA2022001)
  (13, 11, 78, 'A'),(13, 12, 82, 'A'),
  -- Ritu (MBA2022002)
  (14, 11, 90, 'A+'),(14, 12, 93, 'A+');

-- =============================================================================
-- 9. LIBRARY BOOKS
-- =============================================================================
CREATE TABLE library_books (
    book_id     SERIAL PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    author      VARCHAR(150) NOT NULL,
    isbn        VARCHAR(20)  UNIQUE,
    department_id INT REFERENCES departments(department_id),
    total_copies  INT NOT NULL DEFAULT 1,
    available_copies INT NOT NULL DEFAULT 1
);

INSERT INTO library_books (title, author, isbn, department_id, total_copies, available_copies) VALUES
  ('Introduction to Algorithms',          'Cormen et al.',        '9780262033848', 1, 5, 3),
  ('Database System Concepts',            'Silberschatz et al.',  '9780078022159', 1, 4, 2),
  ('Pattern Recognition & Machine Learning','Bishop',             '9780387310732', 1, 3, 1),
  ('VLSI Design Essentials',              'Weste & Harris',       '9780321547743', 2, 3, 3),
  ('Engineering Thermodynamics',          'P.K. Nag',             '9780070435674', 3, 6, 4),
  ('Structural Analysis',                 'R.C. Hibbeler',        '9780132570534', 4, 4, 2),
  ('Higher Engineering Mathematics',      'B.S. Grewal',          '9788174091955', 5, 8, 5),
  ('Concepts of Physics',                 'H.C. Verma',           '9788177091878', 6, 6, 4),
  ('Principles of Marketing',             'Kotler & Armstrong',   '9780133795028', 7, 5, 3),
  ('Financial Management',                'I.M. Pandey',          '9788174465498', 7, 4, 2);

-- =============================================================================
-- 10. BOOK ISSUES  (student ↔ library_book join)
-- =============================================================================
CREATE TABLE book_issues (
    issue_id        SERIAL PRIMARY KEY,
    student_id      INT  NOT NULL REFERENCES students(student_id),
    book_id         INT  NOT NULL REFERENCES library_books(book_id),
    issued_on       DATE NOT NULL,
    due_date        DATE NOT NULL,
    returned_on     DATE,
    fine_amount     NUMERIC(6,2) DEFAULT 0
);

INSERT INTO book_issues (student_id, book_id, issued_on, due_date, returned_on, fine_amount) VALUES
  (1,  1,  '2023-08-10', '2023-08-24', '2023-08-22', 0),
  (1,  2,  '2023-09-01', '2023-09-15', NULL,          0),
  (2,  3,  '2023-08-15', '2023-08-29', '2023-09-05', 70),
  (4,  1,  '2023-09-10', '2023-09-24', NULL,          0),
  (6,  4,  '2023-08-20', '2023-09-03', '2023-09-03',  0),
  (9,  5,  '2023-09-05', '2023-09-19', NULL,          0),
  (11, 6,  '2023-09-12', '2023-09-26', '2023-09-25',  0),
  (13, 9,  '2023-08-05', '2023-08-19', '2023-08-30', 110),
  (14, 10, '2023-08-05', '2023-08-19', '2023-08-20',  10),
  (3,  7,  '2023-09-08', '2023-09-22', NULL,           0);

-- =============================================================================
-- Indexes for common join/filter patterns
-- =============================================================================
CREATE INDEX idx_students_dept     ON students(department_id);
CREATE INDEX idx_students_hostel   ON students(hostel_id);
CREATE INDEX idx_enrollments_stud  ON enrollments(student_id);
CREATE INDEX idx_enrollments_course ON enrollments(course_id);
CREATE INDEX idx_exam_results_stud ON exam_results(student_id);
CREATE INDEX idx_exam_results_exam ON exam_results(exam_id);
CREATE INDEX idx_courses_dept      ON courses(department_id);
CREATE INDEX idx_book_issues_stud  ON book_issues(student_id);
