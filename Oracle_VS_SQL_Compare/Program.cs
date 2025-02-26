using System;
using System.Data;
using System.Data.SqlClient; // For SQL Server
using Oracle.ManagedDataAccess.Client; // For Oracle\
using System.Diagnostics.Eventing.Reader;
using Microsoft.Extensions.Configuration;
using System.Security.Cryptography;
using System.Text;
using System.Runtime.CompilerServices;


namespace Oracle_VS_SQL_Compare
{
    internal class Program
    {
        static string key = "";
        static string logFilePath = "";
        static void Main(string[] args)
        {
            try
            {

            var configuration = new ConfigurationBuilder()
            .SetBasePath(AppContext.BaseDirectory) // Set the base path
            .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true) // Add the appsettings.json file
            .Build();
                createLog();
                WriteLog("DB Compare Utility V1");
                WriteLog("Check VPN Connected (If Required)", true, false);
                //Console.WriteLine("DB Compare Utility V1");
                //Console.WriteLine("Check VPN Connected (If Required)");

                // Create the new log file

                WriteLog("Creating New Log File");

                File.Create(logFilePath).Dispose();

                WriteLog($"Log File: {logFilePath}");

                // SQL Server connection string

                var sqlServerConnectionEncString = configuration["ConnectionStrings:SQLServer"];
                var oracleConnectionEncEncString = configuration["ConnectionStrings:Oracle"];

                WriteLog($"Connecting SQL Server");
                string sqlServerConnectionString = Decrypt(sqlServerConnectionEncString, key);   //"Data Source=sqlmi-usac03-dev-abs.public.632f3ddcf0c7.database.windows.net,3342;Initial Catalog=NXTABS;User ID=NXTAPS;Password=AppsR3@dWr1";
                // Oracle connection string
                WriteLog($"Connecting Oracle");
                string oracleConnectionString = Decrypt(oracleConnectionEncEncString, key); //"DATA SOURCE=(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=10.191.20.75)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=nxtgncdb_pdb1.ncidevdbsubnetp.ncidevvcnphy.oraclevcn.com)));USER ID=NXTABS;PASSWORD=nxtabs";

                WriteLog($"Connecting Database Success");
                // Get table names from both databases
                var sqlServerTables = GetSqlServerTables(sqlServerConnectionString);
                var oracleTables = GetOracleTables(oracleConnectionString);

                // Sort the arrays
                sqlServerTables.Sort();
                oracleTables.Sort();

                WriteLog($"Loading Tables...");

                // Compare the arrays and adjust if needed
                var result = CompareAndAlignTables(sqlServerTables, oracleTables);

                List<Tuple<string, string>> tablesToCompare = new List<Tuple<string, string>>();

                //var tablesToCompare = new List<<string><string>>()
                for (Int32 i = 0; i < result.Item1.Count - 1; i++)
                {
                    tablesToCompare.Add(new Tuple<string, string>(result.Item1[i], result.Item2[i]));
                    //tablesToCompare.Add(result.Item1[i], result.Item2[i]);
                }
                WriteLog($"Comparing Tables...");

                string msg = string.Format("{0,-10} {1,-50} {2,-20} {3,-50} {4,-20} {5,-20}", "Sr No.", "SQL Server Table", "SQL Server Count", "Oracle Table", "Oracle Count", "Differance");
                WriteLog(msg);
                


                // Print table header
                //Console.WriteLine("{0,-10} {1,-50} {2,-20} {3,-50} {4,-20} {5,-20}", "Sr No.", "SQL Server Table", "SQL Server Count", "Oracle Table", "Oracle Count", "Differance");

                // Compare row counts for each pair of tables
                int no = 1;
                foreach (var tablePair in tablesToCompare.ToList())
                {

                    string sqlServerTable = tablePair.Item1;
                    string oracleTable = tablePair.Item2;
                    int sqlServerRowCount = 0;
                    if (sqlServerTable != "")
                    {
                        // SQL Server query
                        string sqlServerQuery = $"SELECT COUNT(*) FROM [{sqlServerTable}]";
                        // Get row count from SQL Server
                        sqlServerRowCount = GetSqlServerRowCount(sqlServerConnectionString, sqlServerQuery);
                    }

                    int oracleRowCount = 0;
                    if (oracleTable != "")
                    {
                        // Oracle query
                        string oracleQuery = $"SELECT COUNT(*) FROM \"{oracleTable}\"";
                        // Get row count from Oracle
                        oracleRowCount = GetOracleRowCount(oracleConnectionString, oracleQuery);
                    }
                    // Print row counts in table format

                    msg = string.Format("{0,-10} {1,-50} {2,-20} {3,-50} {4,-20} {5,-20}", no, sqlServerTable, sqlServerRowCount, oracleTable, oracleRowCount, Math.Abs(sqlServerRowCount - oracleRowCount));
                    WriteLog(msg);
                    //Console.WriteLine("{0,-10} {1,-50} {2,-20} {3,-50} {4,-20} {5,-20}", no, sqlServerTable, sqlServerRowCount, oracleTable, oracleRowCount, Math.Abs(sqlServerRowCount - oracleRowCount));
                    no = no + 1;
                }
            }
            catch (Exception ex)
            {
                WriteLog($"An error occurred: {ex.Message}");
                //Console.WriteLine($"An error occurred: {ex.Message}");
            }
        }

        static int GetSqlServerRowCount(string connectionString, string query)
        {
            int rowCount = 0;

            using (SqlConnection sqlConnection = new SqlConnection(connectionString))
            {
                sqlConnection.Open();

                using (SqlCommand sqlCommand = new SqlCommand(query, sqlConnection))
                {
                    rowCount = (int)sqlCommand.ExecuteScalar();
                }
            }

            return rowCount;
        }

        static int GetOracleRowCount(string connectionString, string query)
        {
            int rowCount = 0;

            using (OracleConnection oracleConnection = new OracleConnection(connectionString))
            {
                oracleConnection.Open();

                using (OracleCommand oracleCommand = new OracleCommand(query, oracleConnection))
                {
                    rowCount = Convert.ToInt32(oracleCommand.ExecuteScalar());
                }
            }

            return rowCount;
        }

        // Function to fetch data from SQL Server
        // Method to compare and align table names

        // Method to get table names from SQL Server
        static List<string> GetSqlServerTables(string connectionString)
        {
            var tables = new List<string>();
            using (SqlConnection connection = new SqlConnection(connectionString))
            {
                connection.Open();
                var query = "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'";
                SqlCommand command = new SqlCommand(query, connection);
                SqlDataReader reader = command.ExecuteReader();
                while (reader.Read())
                {
                    tables.Add(reader["TABLE_NAME"].ToString());
                }
            }
            return tables;
        }

        // Method to get table names from Oracle
        static List<string> GetOracleTables(string connectionString)
        {
            var tables = new List<string>();
            using (OracleConnection connection = new OracleConnection(connectionString))
            {
                connection.Open();
                var query = "SELECT TABLE_NAME FROM USER_TABLES";
                OracleCommand command = new OracleCommand(query, connection);
                OracleDataReader reader = command.ExecuteReader();
                while (reader.Read())
                {
                    tables.Add(reader["TABLE_NAME"].ToString());
                }
            }
            return tables;
        }
        static Tuple<List<string>, List<string>> CompareAndAlignTables(List<string> sqlServerTables, List<string> oracleTables)
        {
            List<string> alignedSqlTables = new List<string>();
            List<string> alignedOracleTables = new List<string>();

            int i = 0, j = 0;
            while (i < sqlServerTables.Count || j < oracleTables.Count)
            {
                if (i < sqlServerTables.Count && j < oracleTables.Count)
                {
                    if (sqlServerTables[i] == oracleTables[j])
                    {
                        alignedSqlTables.Add(sqlServerTables[i]);
                        alignedOracleTables.Add(oracleTables[j]);
                        i++;
                        j++;
                    }
                    else if (string.Compare(sqlServerTables[i], oracleTables[j]) < 0)
                    {
                        alignedSqlTables.Add(sqlServerTables[i]);
                        alignedOracleTables.Add("");  // Insert empty for Oracle
                        i++;
                    }
                    else
                    {
                        alignedSqlTables.Add("");
                        alignedOracleTables.Add(oracleTables[j]);
                        j++;
                    }
                }
                else if (i < sqlServerTables.Count)
                {
                    alignedSqlTables.Add(sqlServerTables[i]);
                    alignedOracleTables.Add("");
                    i++;
                }
                else
                {
                    alignedSqlTables.Add("");
                    alignedOracleTables.Add(oracleTables[j]);
                    j++;
                }
            }

            return Tuple.Create(alignedSqlTables, alignedOracleTables);
        }

        private static string Decrypt(string cipherText, string key)
        {
            byte[] fullCipher = Convert.FromBase64String(cipherText);

            using (Aes aesAlg = Aes.Create())
            {
                aesAlg.Key = Encoding.UTF8.GetBytes(key.PadRight(32).Substring(0, 32)); // Ensure key is 32 bytes for AES-256

                // Extract the IV from the encrypted data
                byte[] iv = new byte[aesAlg.BlockSize / 8];
                byte[] cipher = new byte[fullCipher.Length - iv.Length];

                Array.Copy(fullCipher, iv, iv.Length);
                Array.Copy(fullCipher, iv.Length, cipher, 0, cipher.Length);

                aesAlg.IV = iv;

                using (var decryptor = aesAlg.CreateDecryptor(aesAlg.Key, aesAlg.IV))
                using (var msDecrypt = new MemoryStream(cipher))
                using (var csDecrypt = new CryptoStream(msDecrypt, decryptor, CryptoStreamMode.Read))
                using (var srDecrypt = new StreamReader(csDecrypt))
                {
                    // Read the decrypted bytes into a string
                    return srDecrypt.ReadToEnd();
                }
            }
        }


        public static void WriteLog(string message, bool ShowOnScreen = true, bool WritetoFile = true)
        {
            try
            {
                // Format the message with a timestamp
                string logEntry = $"{DateTime.Now}: {message}";

                // Append the log message to the file
                using (StreamWriter writer = new StreamWriter(logFilePath, true))
                {
                    if (ShowOnScreen)
                    {
                        Console.WriteLine(message);
                    }
                    if (WritetoFile)
                    {
                        writer.WriteLine(logEntry);
                    }
                    
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error writing to log file: {ex.Message}");
            }
        }

        public static void createLog()
        {
            string directoryPath = Directory.GetCurrentDirectory();
            // Create the directory if it doesn't exist
            if (!Directory.Exists(directoryPath))
            {
                Directory.CreateDirectory(directoryPath);
            }

            // Generate a unique log file name using the current timestamp
            string timestamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
            logFilePath = Path.Combine(directoryPath, $"log_{timestamp}.txt");
        }

    }

}


