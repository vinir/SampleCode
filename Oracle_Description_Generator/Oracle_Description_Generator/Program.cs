#define isGenerateAllSPList

using Oracle.ManagedDataAccess.Client;
using Oracle_Description_Generator;
using System;
using System.Drawing;
using System.IO;
using System.IO.Enumeration;
using System.Text;
using System.Xml.Linq;

class Program
{
    static void Main()
    {
        Console.WriteLine("Generating Stored Procedure Information...");

        try
        {
            StringBuilder output = new StringBuilder();
            string fileName = "";
            string connectionString = "DATA SOURCE=(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=10.191.20.75)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=nxtgncdb_pdb1.ncidevdbsubnetp.ncidevvcnphy.oraclevcn.com)));USER ID=NXTABS;PASSWORD=nxtabs"; // Replace with your Oracle Database connection string

            using (OracleConnection connection = new OracleConnection(connectionString))
            {
                connection.Open();
                string oracleTemplatePath = @"D:\\Testing_PoC\\Oracle_Description_Generator\\Oracle_Description_Generator\\Oracle_SP_Summary.txt";
                string fileTemplate = File.ReadAllText(oracleTemplatePath);
                string newSP_Description = "";

                // Retrieve stored procedures information
                using (OracleCommand command = new OracleCommand("select * FROM ALL_OBJECTS where OWNER='NXTABS' AND OBJECT_TYPE = 'PROCEDURE' ORDER BY OBJECT_NAME", connection))
                using (OracleDataReader reader = command.ExecuteReader())
                {
#if !isGenerateAllSPList
                    StringBuilder sbSP = new StringBuilder();
                    while (reader.Read())
                    {
                        sbSP.AppendLine(reader["object_name"].ToString());

                    }

                    string filePathforSPsList = "D:\\Testing_PoC\\Oracle_Description_Generator\\Oracle_Description_Generator\\SPs_Description\\List_SPs.txt";
                    File.WriteAllText(filePathforSPsList, sbSP.ToString());
                    connection.Close();
#else

                    while (reader.Read())
                    {
                        string spName = reader["object_name"].ToString();
                        DateTime createDate = Convert.ToDateTime(reader["created"]);
                        string fileContent = fileTemplate;
                        fileContent = fileContent.Replace("{@SP_Name}",spName);
                        fileContent = fileContent.Replace("{@Date}", createDate.ToShortDateString());
                        fileName = spName;

                        Excel_Data_Retrive edr = new Excel_Data_Retrive();
                        string detals = edr.getValues(spName);
                        if (detals != "")
                        {
                            string[] values = detals.Split("|");
                            fileContent = fileContent.Replace("{@Author}", values[0].ToString());
                            fileContent = fileContent.Replace("{@Description}", values[1].ToString());
                        }
                        else
                        {
                            fileContent = fileContent.Replace("{@Author}", "NA");
                            fileContent = fileContent.Replace("{@Description}", "NA");
                        }
                        
                        

                        string SQLQuery = string.Format("SELECT * FROM ALL_DEPENDENCIES where OWNER='NXTABS' AND NAME ='{0}' AND REFERENCED_TYPE = 'TABLE'", spName);

                        using (OracleCommand infoCommand = new OracleCommand(SQLQuery, connection))
                        {
                            StringBuilder sb = new StringBuilder();
                            using (OracleDataReader infoReader = infoCommand.ExecuteReader())
                            {
                                while (infoReader.Read())
                                {
                                    
                                    sb.Append(infoReader["REFERENCED_NAME"].ToString() + "\r\n");
                                    sb.Append("                     ");
                                                        }
                                fileContent = fileContent.Replace("{@AffectedTables}", sb.ToString());
                                sb.Clear();
                            }
                            
                            
                        }

                        string SQLQueryParam = string.Format("SELECT ARGUMENT_NAME, IN_OUT FROM ALL_ARGUMENTS WHERE OBJECT_NAME = '{0}' AND OWNER = 'NXTABS'", spName);

                        using (OracleCommand infoCommand = new OracleCommand(SQLQueryParam, connection))
                        {
                            StringBuilder sb = new StringBuilder();
                            using (OracleDataReader infoReader = infoCommand.ExecuteReader())
                            {
                                while (infoReader.Read())
                                {
                                    string IN_OUT = infoReader["IN_OUT"].ToString();
                                    if (IN_OUT == "IN")
                                    {
                                        IN_OUT = "";
                                    }
                                    else
                                    {
                                        IN_OUT = " (" + IN_OUT + ")";
                                    }

                                    sb.Append(infoReader["ARGUMENT_NAME"].ToString() + IN_OUT + "\r\n");
                                    sb.Append("                     ");
                            }
                                fileContent = fileContent.Replace("{@Parameters}", sb.ToString());
                                sb.Clear();

                            }
                        }
                        
                        output.AppendLine(fileContent);
                        
                        string filePath = "D:\\Testing_PoC\\Oracle_Description_Generator\\Oracle_Description_Generator\\SPs_Description\\" + fileName + ".txt";
                        File.WriteAllText(filePath, output.ToString());
                        fileContent = "";
                        output.Clear();
                        Console.WriteLine($"Created: {fileName}.txt");
                       // connection.Close();
                    }
#endif
                }

                connection.Close();
                Console.WriteLine("Connection Closed Successfully");

            }

            // Write the generated information to a text file

        }
        catch (Exception ex)
        {
           
            Console.WriteLine($"Error: {ex.Message}");
        }

    }

}
